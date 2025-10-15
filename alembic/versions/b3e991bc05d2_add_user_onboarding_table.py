"""add_user_onboarding_table

Revision ID: b3e991bc05d2
Revises: a12f791bdf77
Create Date: 2025-10-15 09:42:11.483503

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b3e991bc05d2'
down_revision: Union[str, Sequence[str], None] = 'a12f791bdf77'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'user_onboarding',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('completed', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('current_step', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('completed_steps', sa.JSON(), nullable=False, server_default='[]'),
        sa.Column('skipped_steps', sa.JSON(), nullable=False, server_default='[]'),
        sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('user_id')
    )

    # Create index for faster user lookups
    op.create_index('ix_user_onboarding_user_id', 'user_onboarding', ['user_id'])
    op.create_index('ix_user_onboarding_completed', 'user_onboarding', ['completed'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_user_onboarding_completed')
    op.drop_index('ix_user_onboarding_user_id')
    op.drop_table('user_onboarding')
