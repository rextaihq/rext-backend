"""add_user_preferences_table

Revision ID: a12f791bdf77
Revises: f0102d372d26
Create Date: 2025-10-15 09:31:53.173571

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a12f791bdf77'
down_revision: Union[str, Sequence[str], None] = 'f0102d372d26'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'user_preferences',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('theme', sa.String(20), nullable=True, server_default='system'),
        sa.Column('date_format', sa.String(20), nullable=True, server_default='iso'),
        sa.Column('time_format', sa.String(20), nullable=True, server_default='24h'),
        sa.Column('items_per_page', sa.Integer(), nullable=True, server_default='25'),
        sa.Column('sidebar_collapsed', sa.Boolean(), nullable=True, server_default='false'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('user_id', name='uq_user_preferences_user_id')
    )

    # Create index for faster user lookups
    op.create_index('ix_user_preferences_user_id', 'user_preferences', ['user_id'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_user_preferences_user_id', table_name='user_preferences')
    op.drop_table('user_preferences')
