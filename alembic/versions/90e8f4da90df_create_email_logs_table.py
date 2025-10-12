"""create_email_logs_table

Revision ID: 90e8f4da90df
Revises: ddef709e2283
Create Date: 2025-10-11 22:36:04.208738

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '90e8f4da90df'
down_revision: Union[str, Sequence[str], None] = 'ddef709e2283'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'email_logs',
        sa.Column('id', sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('workspace_id', sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey('workspace.id', ondelete='SET NULL'), nullable=True),
        sa.Column('user_id', sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('template_type', sa.String(100), nullable=True),
        sa.Column('provider', sa.String(50), nullable=False),
        sa.Column('provider_message_id', sa.String(255), nullable=True),
        sa.Column('to_email', sa.String(255), nullable=False),
        sa.Column('from_email', sa.String(255), nullable=False),
        sa.Column('subject', sa.String(500), nullable=False),
        sa.Column('status', sa.String(50), nullable=False, server_default='queued'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('delivered_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('failed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('provider_response', sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column('tags', sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # Create indexes
    op.create_index('idx_email_logs_workspace', 'email_logs', ['workspace_id'])
    op.create_index('idx_email_logs_user', 'email_logs', ['user_id'])
    op.create_index('idx_email_logs_status', 'email_logs', ['status'])
    op.create_index('idx_email_logs_provider_message_id', 'email_logs', ['provider_message_id'])
    op.create_index('idx_email_logs_created_at', 'email_logs', ['created_at'])
    op.create_index('idx_email_logs_to_email', 'email_logs', ['to_email'])


def downgrade() -> None:
    """Downgrade schema."""
    # Drop indexes first
    op.drop_index('idx_email_logs_to_email', table_name='email_logs')
    op.drop_index('idx_email_logs_created_at', table_name='email_logs')
    op.drop_index('idx_email_logs_provider_message_id', table_name='email_logs')
    op.drop_index('idx_email_logs_status', table_name='email_logs')
    op.drop_index('idx_email_logs_user', table_name='email_logs')
    op.drop_index('idx_email_logs_workspace', table_name='email_logs')

    # Drop table
    op.drop_table('email_logs')
