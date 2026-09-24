"""Remove the brand_voice.delete permission (no delete functionality).

Revision ID: 20260921bvdelete
Revises: 20260921billfix

Brand voice has no delete functionality in the product: the UI never offered
a delete action, and the orphaned DELETE /workspaces/{id}/brand-voice route
(plus BrandVoiceService.delete_brand_voice) has been removed from the code.
The permission row and its workspace_owner/workspace_admin grants are now
dead weight and are deleted so they stop appearing in role permission
dialogs as an assignable-but-useless option.

Idempotent. Downgrade intentionally restores nothing.
"""

from alembic import op

revision = "20260921bvdelete"
down_revision = "20260921billfix"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Grants first (permission row is referenced by them), then the permission.
    op.execute(
        """
        DELETE FROM role_permissions rp
        USING permissions p
        WHERE rp.permission_id = p.id AND p.name = 'brand_voice.delete'
        """
    )
    op.execute(
        """
        DELETE FROM permissions WHERE name = 'brand_voice.delete'
        """
    )


def downgrade() -> None:
    # The route and UI are gone; restoring a permission nothing checks
    # would only resurrect a dead option in permission dialogs.
    pass
