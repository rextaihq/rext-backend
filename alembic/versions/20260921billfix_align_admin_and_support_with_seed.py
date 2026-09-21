"""Align admin/support grants with the canonical seed (billing drift fix).

Revision ID: 20260921billfix
Revises: 20260921nofloor

The local (and possibly staging/production) databases drifted from
``scripts/seeds/seed_permissions.py`` — the canonical RBAC matrix — because
the seed is additive-only by design and never removes grants:

- ``admin`` holds ``billing.manage`` it should not have. It most likely
  arrived via the ``subscription.manage`` -> ``billing.manage`` conversion
  (admin held ``subscription.manage`` before the billing rename). SEC-RBAC-11
  (tests/test_rbac_permission_floor.py) pins admin as "everything except
  billing.manage": ``billing.read`` stays, ``billing.manage`` is
  super_admin-only. The revoke closes an over-grant: admin subscription
  writes (refunds, retries, plan writes) already check ``billing.manage``.
- ``support`` is missing ``user.read``. The seed includes it so support can
  open user accounts read-only while investigating.

Both changes are idempotent. Downgrade intentionally restores nothing.
After deploying, flush the Redis permission cache (``user:permissions:*``).
"""

from alembic import op

revision = "20260921billfix"
down_revision = "20260921nofloor"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. admin: revoke billing.manage (SEC-RBAC-11 — super_admin only).
    op.execute(
        """
        DELETE FROM role_permissions rp
        USING roles r, permissions p
        WHERE rp.role_id = r.id AND rp.permission_id = p.id
          AND r.name = 'admin' AND p.name = 'billing.manage'
        """
    )

    # 2. support: ensure user.read (idempotent).
    op.execute(
        """
        INSERT INTO role_permissions (id, role_id, permission_id, created_at)
        SELECT gen_random_uuid(), r.id, p.id, NOW()
        FROM roles r JOIN permissions p ON p.name = 'user.read'
        WHERE r.name = 'support'
          AND NOT EXISTS (
              SELECT 1 FROM role_permissions rp
              WHERE rp.role_id = r.id AND rp.permission_id = p.id
          )
        """
    )


def downgrade() -> None:
    # Grant removals are not restored (house convention); the support
    # user.read grant is likewise left in place.
    pass
