"""add_discount_usage_table

Revision ID: efa024600a98
Revises: 33eb548e7bd9
Create Date: 2025-10-18 15:04:11.410387

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'efa024600a98'
down_revision: Union[str, Sequence[str], None] = '33eb548e7bd9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create discount_usage table
    op.create_table(
        'discount_usage',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('discount_code', sa.String(100), nullable=False),
        sa.Column('discount_amount', sa.Numeric(10, 2), nullable=True),
        sa.Column('discount_amount_type', sa.String(20), nullable=True),  # 'percent' or 'fixed'
        sa.Column('subscription_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('order_id', sa.String(255), nullable=True),
        sa.Column('lemonsqueezy_discount_id', sa.String(255), nullable=True),
        sa.Column('applied_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('usage_metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['subscription_id'], ['user_subscriptions.id'], ondelete='SET NULL')
    )

    # Create indexes for performance
    op.create_index('idx_discount_usage_user_id', 'discount_usage', ['user_id'])
    op.create_index('idx_discount_usage_code', 'discount_usage', ['discount_code'])
    op.create_index('idx_discount_usage_applied_at', 'discount_usage', ['applied_at'])
    op.create_index('idx_discount_usage_subscription_id', 'discount_usage', ['subscription_id'])


def downgrade() -> None:
    """Downgrade schema."""
    # Drop indexes
    op.drop_index('idx_discount_usage_subscription_id', table_name='discount_usage')
    op.drop_index('idx_discount_usage_applied_at', table_name='discount_usage')
    op.drop_index('idx_discount_usage_code', table_name='discount_usage')
    op.drop_index('idx_discount_usage_user_id', table_name='discount_usage')

    # Drop table
    op.drop_table('discount_usage')
