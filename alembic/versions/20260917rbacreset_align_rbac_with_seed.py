"""Align RBAC data with the seed definitions and enforce one owner per workspace.

Revision ID: 20260917rbacreset
Revises: 20260916permcleanup

- email.resend: never used by a route guard (resend is gated by audit.read).
- brand_voice.create: brand voice is upserted under brand_voice.update.
- support.view_workspace / support.view_billing: replaced by workspace.read
  and billing.read long ago; no guard references them.
- permission.delete: permissions are seeded and can only be edited.
- editor loses content.publish: publishing is a workspace_admin+ action.
- admin holds every permission except billing.manage; super_admin holds all.
- user_roles gets a trigger so a workspace can carry at most one
  workspace_owner row. The role is matched by name, not id, so the same
  migration works on every environment regardless of seeded ids.

Deleted permissions and grants are not restored on downgrade.
"""

from alembic import op

revision = "20260917rbacreset"
down_revision = "20260916permcleanup"
branch_labels = None
depends_on = None

REMOVED_PERMISSIONS = [
    "email.resend",
    "brand_voice.create",
    "support.view_workspace",
    "support.view_billing",
    "permission.delete",
]

SINGLE_OWNER_FN = """
CREATE OR REPLACE FUNCTION enforce_single_workspace_owner() RETURNS trigger AS $$
BEGIN
    IF NEW.workspace_id IS NOT NULL
       AND EXISTS (SELECT 1 FROM roles WHERE id = NEW.role_id AND name = 'workspace_owner')
       AND EXISTS (
           SELECT 1 FROM user_roles ur
           JOIN roles r ON r.id = ur.role_id
           WHERE ur.workspace_id = NEW.workspace_id
             AND r.name = 'workspace_owner'
             AND ur.id <> NEW.id
       )
    THEN
        RAISE EXCEPTION 'workspace % already has a workspace_owner', NEW.workspace_id
            USING ERRCODE = 'unique_violation';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""


def upgrade() -> None:
    names = ", ".join(f"'{name}'" for name in REMOVED_PERMISSIONS)
    op.execute(
        f"DELETE FROM role_permissions WHERE permission_id IN (SELECT id FROM permissions WHERE name IN ({names}))"
    )
    op.execute(f"DELETE FROM permissions WHERE name IN ({names})")

    op.execute("""
        DELETE FROM role_permissions rp
        USING roles r, permissions p
        WHERE rp.role_id = r.id AND rp.permission_id = p.id
          AND r.name = 'editor' AND p.name = 'content.publish'
    """)

    op.execute("""
        INSERT INTO role_permissions (id, role_id, permission_id, created_at)
        SELECT gen_random_uuid(), r.id, p.id, NOW()
        FROM roles r CROSS JOIN permissions p
        WHERE (r.name = 'super_admin' OR (r.name = 'admin' AND p.name <> 'billing.manage'))
          AND NOT EXISTS (
              SELECT 1 FROM role_permissions rp WHERE rp.role_id = r.id AND rp.permission_id = p.id
          )
    """)

    op.execute(SINGLE_OWNER_FN)
    op.execute("""
        CREATE TRIGGER trg_single_workspace_owner
        BEFORE INSERT OR UPDATE OF role_id, workspace_id ON user_roles
        FOR EACH ROW EXECUTE FUNCTION enforce_single_workspace_owner()
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_single_workspace_owner ON user_roles")
    op.execute("DROP FUNCTION IF EXISTS enforce_single_workspace_owner()")
    # Removed permissions and changed grants are intentionally not restored.
