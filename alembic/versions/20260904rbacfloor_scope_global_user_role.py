"""scope the global 'user' role to platform-only permissions

Revision ID: 20260904rbacfloor
Revises: 20260903usagehr, 20260904isperm
Create Date: 2026-09-04

get_user_permissions() unions workspace-scoped roles with global ones
(workspace_id IS NULL), so anything on the global 'user' role becomes a
permission floor under EVERY workspace. seed006/seed009 put workspace
resources on it (member.read, content.read, topic.read, knowledge.read,
media.read/view, workspace.read, audit.*), which made the floor higher than
the whole 'viewer' role: viewer granted nothing on top of it, and demoting
someone to viewer removed nothing. Editing the viewer role could not fix
that - the permissions were never coming from viewer.

This trims the global role back to AuthService.DEFAULT_PERMISSIONS, the four
permissions that mean something without a workspace. Workspace access now
comes only from the workspace-scoped row, so both promotion and demotion
take effect.

member.read went onto the global role because three self-service invitation
endpoints gated on it globally. Those only ever return the caller's own
invitations, so they are ungated in the same change (see
src/api/routes/users/invitations.py and workspace_invitations.py).

Also removes user_roles rows that pair a workspace role (is_workspace_role)
with workspace_id IS NULL - those grant that role in every workspace at
once. RoleService.assign_role now rejects new ones.
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "20260904rbacfloor"
down_revision: Union[str, Sequence[str], None] = "20260904mrgheads"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Mirrors AuthService.DEFAULT_PERMISSIONS - keep the two in sync.
# Permissions that mean something WITHOUT a workspace. licenses are keyed on
# user_id with no workspace_id, so they belong here - a license is owned by the
# person, not by a workspace.
PLATFORM_PERMISSIONS = (
    "user.read",
    "user.update",
    "workspace.create",
    "subscription.read",
    "license.read",
    "license.view",
)

# What seed006/seed009/b61d3f424d6f put on the global role that belongs to a
# workspace instead. Listed explicitly so downgrade() can restore exactly it.
WORKSPACE_PERMISSIONS_ON_GLOBAL_ROLE = (
    "member.read",
    "workspace.read",
    "content.read",
    "topic.read",
    "knowledge.read",
    "media.read",
    "media.view",
    "audit.read",
    "audit.write",
    "audit.export",
)


def upgrade() -> None:
    conn = op.get_bind()

    # 1. Drop global rows holding a workspace role. Done before the backfill
    #    below so a user whose only global row was one of these (assigned via
    #    the admin dialog with workspace_id = null) picks up 'user' instead.
    result = conn.execute(sa.text("""
        DELETE FROM user_roles ur
        USING roles r
        WHERE ur.role_id = r.id
          AND ur.workspace_id IS NULL
          AND r.is_workspace_role IS TRUE;
    """))
    print(f"Removed {result.rowcount} unscoped workspace-role assignment(s)")

    # 2. Backfill the global 'user' role for anyone left without a platform
    #    role. Invited users who never registered normally, and OAuth users
    #    whose is_primary global row was a workspace role, both land here.
    result = conn.execute(sa.text("""
        INSERT INTO user_roles (id, user_id, role_id, workspace_id, assigned_by_user_id, is_primary, assigned_at)
        SELECT gen_random_uuid(), u.id, r.id, NULL, u.id, TRUE, NOW()
        FROM users u CROSS JOIN roles r
        WHERE r.name = 'user'
          AND NOT EXISTS (
              SELECT 1 FROM user_roles ur
              JOIN roles r2 ON r2.id = ur.role_id
              WHERE ur.user_id = u.id
                AND ur.workspace_id IS NULL
                AND r2.is_workspace_role IS NOT TRUE
          );
    """))
    print(f"Backfilled global 'user' role for {result.rowcount} user(s)")

    # 3. Backfill workspace-scoped roles for members that have none.
    #    MemberService.get_workspace_members_with_users self-heals this at read
    #    time, which proves it happens in practice. Until now those members
    #    still worked, because the global 'user' role handed them content.read,
    #    workspace.read and friends in every workspace. Step 4 removes that
    #    safety net, so anyone still missing a workspace role would be locked
    #    out of a workspace they legitimately belong to. Same recovery order as
    #    the self-heal: workspace owner -> accepted invitation's role -> viewer.
    result = conn.execute(sa.text("""
        WITH resolved AS (
            SELECT
                m.user_id,
                m.workspace_id,
                COALESCE(
                    CASE WHEN w.user_id = m.user_id THEN
                        (SELECT id FROM roles WHERE name = 'workspace_owner' AND is_workspace_role IS TRUE)
                    END,
                    (SELECT i.role_id FROM user_invitations i
                      JOIN users u ON lower(u.email) = lower(i.email)
                     WHERE u.id = m.user_id
                       AND i.workspace_id = m.workspace_id
                       AND i.status = 'accepted'
                       AND i.role_id IS NOT NULL
                     ORDER BY i.created_at DESC
                     LIMIT 1),
                    (SELECT id FROM roles WHERE name = 'viewer' AND is_workspace_role IS TRUE)
                ) AS role_id
            FROM workspace_members m
            JOIN workspace w ON w.id = m.workspace_id
            WHERE NOT EXISTS (
                SELECT 1 FROM user_roles ur
                WHERE ur.user_id = m.user_id AND ur.workspace_id = m.workspace_id
            )
        )
        INSERT INTO user_roles (id, user_id, role_id, workspace_id, assigned_by_user_id, is_primary, assigned_at)
        SELECT gen_random_uuid(), r.user_id, r.role_id, r.workspace_id, r.user_id, TRUE, NOW()
        FROM resolved r
        WHERE r.role_id IS NOT NULL;
    """))
    print(f"Backfilled workspace role for {result.rowcount} member(s) that had none")

    # 4. Trim the global role to platform-only permissions.
    result = conn.execute(
        sa.text("""
            DELETE FROM role_permissions rp
            USING roles r, permissions p
            WHERE rp.role_id = r.id
              AND rp.permission_id = p.id
              AND r.name = 'user'
              AND p.name NOT IN :keep;
        """).bindparams(sa.bindparam("keep", value=PLATFORM_PERMISSIONS, expanding=True))
    )
    print(f"Removed {result.rowcount} workspace permission(s) from the global 'user' role")

    # Make sure the four it should have are actually there.
    conn.execute(
        sa.text("""
            INSERT INTO role_permissions (id, role_id, permission_id, created_at)
            SELECT gen_random_uuid(), r.id, p.id, NOW()
            FROM roles r CROSS JOIN permissions p
            WHERE r.name = 'user'
              AND p.name IN :keep
              AND NOT EXISTS (
                  SELECT 1 FROM role_permissions rp
                  WHERE rp.role_id = r.id AND rp.permission_id = p.id
              );
        """).bindparams(sa.bindparam("keep", value=PLATFORM_PERMISSIONS, expanding=True))
    )


def downgrade() -> None:
    # Only the permission trim is reversible. The deleted user_roles rows were
    # a misconfiguration and the backfilled ones are harmless, so neither is
    # undone.
    conn = op.get_bind()
    conn.execute(
        sa.text("""
            INSERT INTO role_permissions (id, role_id, permission_id, created_at)
            SELECT gen_random_uuid(), r.id, p.id, NOW()
            FROM roles r CROSS JOIN permissions p
            WHERE r.name = 'user'
              AND p.name IN :restore
              AND NOT EXISTS (
                  SELECT 1 FROM role_permissions rp
                  WHERE rp.role_id = r.id AND rp.permission_id = p.id
              );
        """).bindparams(
            sa.bindparam("restore", value=WORKSPACE_PERMISSIONS_ON_GLOBAL_ROLE, expanding=True)
        )
    )
