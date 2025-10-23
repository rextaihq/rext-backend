"""Add reminder_sent field to user_invitations

Revision ID: inv001
Revises: seed008
Create Date: 2025-10-23

Add reminder_sent boolean field to track whether expiry reminder emails
have been sent for pending invitations.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'inv001'
down_revision = 'seed008'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add reminder_sent field to user_invitations table."""
    op.add_column(
        'user_invitations',
        sa.Column('reminder_sent', sa.Boolean(), nullable=False, server_default='false')
    )


def downgrade() -> None:
    """Remove reminder_sent field from user_invitations table."""
    op.drop_column('user_invitations', 'reminder_sent')
