"""Add accepted_at column to user_invitations

Revision ID: inv003
Revises: 144096b38f85
Create Date: 2026-03-25

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'inv003'
down_revision = ('263449deebd4', '625b40a3c6ba')
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add accepted_at field to user_invitations table."""
    op.add_column(
        'user_invitations',
        sa.Column('accepted_at', sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    """Remove accepted_at field from user_invitations table."""
    op.drop_column('user_invitations', 'accepted_at')
