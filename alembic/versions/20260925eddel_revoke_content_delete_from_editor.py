"""Revoke content.delete from the editor role.

Revision ID: 20260925eddel
Revises: 20260922persona

Production issue #4: the editor role carries ``content.delete`` on production
but not on staging. No seed or migration ever granted it — the seeder
(scripts/seeds/seed_permissions.py) is additive-only, so a historical grant on
production survived every later seed run, while a freshly-seeded staging
database never received it. Per ROLE_PERMISSIONS_AUDIT.md, content.delete
belongs to workspace_owner / workspace_admin (and platform admins) only.

Grant removal is not restored on downgrade.

After deploying, flush the Redis permission cache (``user:permissions:*``) so
the revocation is visible immediately instead of after the 5-minute TTL.
"""

from alembic import op

revision = "20260925eddel"
down_revision = "20260922persona"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DELETE FROM role_permissions rp
        USING roles r, permissions p
        WHERE rp.role_id = r.id AND rp.permission_id = p.id
          AND r.name = 'editor'
          AND p.name = 'content.delete'
        """
    )


def downgrade() -> None:
    pass
