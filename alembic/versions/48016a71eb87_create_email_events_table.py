"""create_email_events_table

Revision ID: 48016a71eb87
Revises: 90e8f4da90df
Create Date: 2025-10-11 22:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '48016a71eb87'
down_revision: Union[str, Sequence[str], None] = '90e8f4da90df'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'email_events',
        sa.Column('id', sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('email_log_id', sa.dialects.postgresql.UUID(as_uuid=True), sa.ForeignKey('email_logs.id', ondelete='SET NULL'), nullable=True),
        sa.Column('provider', sa.String(50), nullable=False),
        sa.Column('provider_event_id', sa.String(255), nullable=False, unique=True),
        sa.Column('provider_message_id', sa.String(255), nullable=False),
        sa.Column('event_type', sa.String(50), nullable=False),
        sa.Column('event_data', sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column('received_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # Create indexes
    op.create_index('idx_email_events_log', 'email_events', ['email_log_id'])
    op.create_index('idx_email_events_provider_message', 'email_events', ['provider_message_id'])
    op.create_index('idx_email_events_type', 'email_events', ['event_type'])
    op.create_index('idx_email_events_received_at', 'email_events', ['received_at'])


def downgrade() -> None:
    """Downgrade schema."""
    # Drop indexes first
    op.drop_index('idx_email_events_received_at', table_name='email_events')
    op.drop_index('idx_email_events_type', table_name='email_events')
    op.drop_index('idx_email_events_provider_message', table_name='email_events')
    op.drop_index('idx_email_events_log', table_name='email_events')

    # Drop table
    op.drop_table('email_events')
