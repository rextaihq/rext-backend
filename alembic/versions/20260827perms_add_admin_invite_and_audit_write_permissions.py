"""add admin.invite and audit.write permissions

Revision ID: 20260827perms
Revises: f0c503357612
Create Date: 2026-08-27

Several routes reference permissions that were never created by any migration:

- ``admin.invite``  -> platform admin invitation management
  (src/api/routes/admin/admin_invitation_routes.py, admin_invitation_service.py)
- ``audit.write``   -> resolve/modify monitoring records
  (src/api/routes/admin/monitoring_routes.py:resolve_error_log)

Until now those endpoints returned 403 for every caller because the required
permission did not exist in the ``permissions`` table. This migration creates
them and assigns them following the RBAC matrix in
``scripts/seeds/seed_permissions.py``:

- ``admin.invite`` -> super_admin
- ``audit.write``  -> super_admin, admin

NOTE: ``audit.admin`` is intentionally NOT created. Routes that used it were
migrated to ``audit.read`` (PR #635 / #636 / #638).
"""
from alembic import op


revision = "20260827perms"
down_revision = "f0c503357612"
branch_labels = None
depends_on = None


PERMISSIONS = [
    # (name, display_name, description, resource, action)
    ("admin.invite", "Invite Platform Admins",
     "Create and manage platform administrator invitations", "admin", "invite"),
    ("audit.write", "Write Audit / Monitoring Records",
     "Modify audit and monitoring records (e.g. resolve error logs)", "audit", "write"),
]

ROLE_ASSIGNMENTS = {
    "admin.invite": ["super_admin"],
    "audit.write": ["super_admin", "admin"],
}


def upgrade() -> None:
    for name, display_name, description, resource, action in PERMISSIONS:
        op.execute(
            f"""
            INSERT INTO permissions (id, name, display_name, description, resource, action, created_at)
            SELECT gen_random_uuid(), '{name}', '{display_name}', '{description}', '{resource}', '{action}', NOW()
            WHERE NOT EXISTS (SELECT 1 FROM permissions WHERE name = '{name}')
            """
        )

    for perm_name, role_names in ROLE_ASSIGNMENTS.items():
        role_list = ", ".join(f"'{r}'" for r in role_names)
        op.execute(
            f"""
            INSERT INTO role_permissions (id, role_id, permission_id, created_at)
            SELECT gen_random_uuid(), r.id, p.id, NOW()
            FROM roles r
            CROSS JOIN permissions p
            WHERE r.name IN ({role_list})
              AND p.name = '{perm_name}'
              AND NOT EXISTS (
                  SELECT 1 FROM role_permissions rp
                  WHERE rp.role_id = r.id AND rp.permission_id = p.id
              )
            """
        )


def downgrade() -> None:
    for name, *_ in PERMISSIONS:
        op.execute(
            f"DELETE FROM role_permissions WHERE permission_id = "
            f"(SELECT id FROM permissions WHERE name = '{name}')"
        )
        op.execute(f"DELETE FROM permissions WHERE name = '{name}'")
