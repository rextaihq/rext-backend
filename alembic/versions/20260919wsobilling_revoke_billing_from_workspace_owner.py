"""Revoke billing.read / billing.manage from workspace_owner.

Revision ID: 20260919wsobilling
Revises: 20260918rbacfix

seed009 granted both to workspace_owner; the seed dropped them long ago but is
additive-only, so the rows survived. Every billing.* route is global-scoped
(workspace_scoped=False), so a workspace role can never use them. Billing is a
platform-admin concern.

Grant removal is not restored on downgrade.
"""

from alembic import op

revision = "20260919wsobilling"
down_revision = "20260918rbacfix"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DELETE FROM role_permissions rp
        USING roles r, permissions p
        WHERE rp.role_id = r.id AND rp.permission_id = p.id
          AND r.name = 'workspace_owner'
          AND p.name IN ('billing.read', 'billing.manage')
        """
    )


def downgrade() -> None:
    pass
