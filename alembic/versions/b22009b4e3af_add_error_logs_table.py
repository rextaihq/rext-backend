"""add_error_logs_table

Revision ID: b22009b4e3af
Revises: 02b176385c4f
Create Date: 2025-10-13 09:31:58.094689

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b22009b4e3af'
down_revision: Union[str, Sequence[str], None] = '02b176385c4f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    from sqlalchemy.dialects import postgresql

    op.create_table(
        'error_logs',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('severity', sa.String(length=20), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('source', sa.String(length=255), nullable=True),
        sa.Column('user_id', sa.UUID(), nullable=True),
        sa.Column('request_id', sa.String(length=100), nullable=True),
        sa.Column('stack_trace', sa.Text(), nullable=True),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True, server_default='{}'),
        sa.Column('resolved', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('resolved_by', sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(['resolved_by'], ['users.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_error_logs_timestamp', 'error_logs', ['timestamp'])
    op.create_index('ix_error_logs_severity', 'error_logs', ['severity'])
    op.create_index('ix_error_logs_resolved', 'error_logs', ['resolved'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_error_logs_resolved', 'error_logs')
    op.drop_index('ix_error_logs_severity', 'error_logs')
    op.drop_index('ix_error_logs_timestamp', 'error_logs')
    op.drop_table('error_logs')
