"""Remove the platform-floor 'user' role (RBAC floor cleanup).

Revision ID: 20260921nofloor
Revises: 20260918wscreate

The global ``user`` role was the platform floor: auto-assigned to every
account at signup and carrying ``user.read``/``user.update``/``license.read``/
``license.view``. Those grants were redundant — every own-account route that
checked them is now gated on authentication alone (profile, sessions,
password, preferences, onboarding, notifications; workspace creation and
license listing were already authentication-only) — so the role carried no
effective permissions and has been removed from the application code
(signup no longer assigns it, and RoleService no longer refuses its
revocation).

This migration deletes, in FK-safe order:

1. ``user_roles`` rows assigning the ``user`` role (one per account);
2. ``user_invitations`` rows targeting it (legacy anomalies — the column is
   NOT NULL with ON DELETE RESTRICT and the role is not a workspace role,
   so such invitations were never meaningful);
3. its ``role_permissions`` rows;
4. the role itself.

The ``user.read``/``user.update``/``license.*`` permissions remain in the
``permissions`` table: admin/support still hold ``user.read``/``user.update``
for cross-account admin routes, and the email preview endpoints still check
``user.read``.

After deploying, flush the Redis permission cache (``user:permissions:*``).
The downgrade recreates an empty ``user`` role and does NOT restore any
assignments or grants.
"""

from alembic import op

revision = "20260921nofloor"
down_revision = "20260918wscreate"
branch_labels = None
depends_on = None

# Exact table names, verified against the live schema.
USER_ROLES_TABLE = "user_roles"
INVITATIONS_TABLE = "user_invitations"
ROLE_PERMISSIONS_TABLE = "role_permissions"
ROLES_TABLE = "roles"


def upgrade() -> None:
    # 1. Drop every account's assignment of the floor role.
    op.execute(
        f"""
        DELETE FROM {USER_ROLES_TABLE} ur
        USING {ROLES_TABLE} r
        WHERE ur.role_id = r.id AND r.name = 'user'
        """
    )

    # 2. Drop legacy invitations targeting the floor role (RESTRICT FK,
    #    NOT NULL column: deleting the rows is the only sound option).
    op.execute(
        f"""
        DELETE FROM {INVITATIONS_TABLE} i
        USING {ROLES_TABLE} r
        WHERE i.role_id = r.id AND r.name = 'user'
        """
    )

    # 3. Drop the floor role's permission grants.
    op.execute(
        f"""
        DELETE FROM {ROLE_PERMISSIONS_TABLE} rp
        USING {ROLES_TABLE} r
        WHERE rp.role_id = r.id AND r.name = 'user'
        """
    )

    # 4. Drop the role itself.
    op.execute(
        f"""
        DELETE FROM {ROLES_TABLE} WHERE name = 'user'
        """
    )


def downgrade() -> None:
    # Recreate the empty role only. Assignments and grants are not restored:
    # the application no longer assigns it, and re-granting the old floor
    # permissions would re-introduce the redundancy this migration removed.
    op.execute(
        f"""
        INSERT INTO {ROLES_TABLE} (id, name, display_name, description,
                                   hierarchy_level, is_system_role,
                                   is_workspace_role, created_at)
        SELECT gen_random_uuid(), 'user', 'User',
               'Default role for regular users (removed; empty placeholder)',
               1, true, false, NOW()
        WHERE NOT EXISTS (SELECT 1 FROM {ROLES_TABLE} WHERE name = 'user')
        """
    )
