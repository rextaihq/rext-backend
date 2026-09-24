"""Introduce user.manage and tighten role grants (RBAC audit 2026-09-16 fixes).

Revision ID: 20260918rbacfix
Revises: 20260917rbacreset

Security fixes from RBAC_SECURITY_AUDIT_2026-09-16.md:

- SEC-RBAC-01/02/03: add the admin-only ``user.manage`` permission and grant it
  to ``admin`` and ``super_admin`` only. The cross-user admin routes (list all
  users, edit/suspend/ban/delete any account) move onto it in code, so the
  default ``user`` role's self-service ``user.read``/``user.update`` no longer
  reach them. The ``user`` role is deliberately left untouched.
- SEC-RBAC-15: revoke the ineffective ``role.read`` from ``workspace_admin``
  (every role.* route is global-scoped).
- Grant ``billing.read`` to ``support`` so it can view the admin Subscriptions
  and Refund Management pages; every billing write still needs ``billing.manage``.

Grants are made by explicit role name, never a CROSS JOIN over all permissions
(SEC-RBAC-11), so no unrelated permission is swept onto admin.

After deploying, flush the Redis permission cache (``user:permissions:*``).
Grant removals are not restored on downgrade.
"""

from alembic import op

revision = "20260918rbacfix"
down_revision = "20260917rbacreset"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Create user.manage (idempotent).
    op.execute(
        """
        INSERT INTO permissions (id, name, display_name, description, resource, action, is_system, created_at)
        SELECT gen_random_uuid(), 'user.manage', 'Manage Users',
               'List, edit, suspend, ban and manage other users'' accounts',
               'user', 'manage', true, NOW()
        WHERE NOT EXISTS (SELECT 1 FROM permissions WHERE name = 'user.manage')
        """
    )

    # 2. Grant user.manage to admin and super_admin only (explicit, no CROSS JOIN).
    op.execute(
        """
        INSERT INTO role_permissions (id, role_id, permission_id, created_at)
        SELECT gen_random_uuid(), r.id, p.id, NOW()
        FROM roles r CROSS JOIN permissions p
        WHERE r.name IN ('admin', 'super_admin')
          AND p.name = 'user.manage'
          AND NOT EXISTS (
              SELECT 1 FROM role_permissions rp
              WHERE rp.role_id = r.id AND rp.permission_id = p.id
          )
        """
    )

    # 3. Grant billing.read to support (idempotent, by name).
    op.execute(
        """
        INSERT INTO role_permissions (id, role_id, permission_id, created_at)
        SELECT gen_random_uuid(), r.id, p.id, NOW()
        FROM roles r JOIN permissions p ON p.name = 'billing.read'
        WHERE r.name = 'support'
          AND NOT EXISTS (
              SELECT 1 FROM role_permissions rp
              WHERE rp.role_id = r.id AND rp.permission_id = p.id
          )
        """
    )

    # 4. Revoke ineffective role.read from workspace_admin (SEC-RBAC-15).
    op.execute(
        """
        DELETE FROM role_permissions rp
        USING roles r, permissions p
        WHERE rp.role_id = r.id AND rp.permission_id = p.id
          AND r.name = 'workspace_admin' AND p.name = 'role.read'
        """
    )


def downgrade() -> None:
    # Remove the user.manage grants and the permission itself. The role.read
    # revocation and the support billing.read grant are intentionally left as-is.
    op.execute(
        """
        DELETE FROM role_permissions rp
        USING permissions p
        WHERE rp.permission_id = p.id AND p.name = 'user.manage'
        """
    )
    op.execute("DELETE FROM permissions WHERE name = 'user.manage'")
