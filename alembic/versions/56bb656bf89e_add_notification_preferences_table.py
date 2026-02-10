"""add notification preferences table

Revision ID: 56bb656bf89e
Revises: f9e8d7c6b5a4
Create Date: 2025-10-02 20:42:28.433004

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import uuid


# revision identifiers, used by Alembic.
revision: str = '56bb656bf89e'
down_revision: Union[str, Sequence[str], None] = 'f9e8d7c6b5a4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create notification_preferences table
    op.create_table(
        'notification_preferences',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('email_notifications', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('email_digest_frequency', sa.String(20), nullable=False, server_default='daily'),
        sa.Column('email_workspace_invites', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('email_comments', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('email_mentions', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('email_updates', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('in_app_notifications', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('in_app_workspace_invites', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('in_app_comments', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('in_app_mentions', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('in_app_updates', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.TIMESTAMP(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.TIMESTAMP(), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('user_id', name='uq_notification_preferences_user_id')
    )

    # Add index on user_id for faster lookups
    op.create_index('ix_notification_preferences_user_id', 'notification_preferences', ['user_id'])


def downgrade() -> None:
    """Downgrade schema."""
    # Drop index first
    op.drop_index('ix_notification_preferences_user_id', table_name='notification_preferences')

    # Drop table
    op.drop_table('notification_preferences')
