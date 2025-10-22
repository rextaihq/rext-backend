"""add_refunds_table

Revision ID: 8021696d2e4f
Revises: 1318ededff9c
Create Date: 2025-10-19 08:34:19.001524

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8021696d2e4f'
down_revision: Union[str, Sequence[str], None] = '1318ededff9c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create refunds table
    op.create_table(
        'refunds',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('subscription_id', sa.UUID(), nullable=True),
        sa.Column('lemonsqueezy_order_id', sa.String(), nullable=False),
        sa.Column('lemonsqueezy_refund_id', sa.String(), nullable=True),
        sa.Column('refund_amount', sa.Integer(), nullable=False),
        sa.Column('original_amount', sa.Integer(), nullable=False),
        sa.Column('currency', sa.String(length=3), nullable=False, server_default='USD'),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='pending'),
        sa.Column('is_partial', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('processed_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['subscription_id'], ['user_subscriptions.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # Create indexes
    op.create_index(op.f('ix_refunds_user_id'), 'refunds', ['user_id'], unique=False)
    op.create_index(op.f('ix_refunds_subscription_id'), 'refunds', ['subscription_id'], unique=False)
    op.create_index(op.f('ix_refunds_lemonsqueezy_order_id'), 'refunds', ['lemonsqueezy_order_id'], unique=False)
    op.create_index(op.f('ix_refunds_lemonsqueezy_refund_id'), 'refunds', ['lemonsqueezy_refund_id'], unique=False)
    op.create_index(op.f('ix_refunds_status'), 'refunds', ['status'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    # Drop indexes
    op.drop_index(op.f('ix_refunds_status'), table_name='refunds')
    op.drop_index(op.f('ix_refunds_lemonsqueezy_refund_id'), table_name='refunds')
    op.drop_index(op.f('ix_refunds_lemonsqueezy_order_id'), table_name='refunds')
    op.drop_index(op.f('ix_refunds_subscription_id'), table_name='refunds')
    op.drop_index(op.f('ix_refunds_user_id'), table_name='refunds')

    # Drop table
    op.drop_table('refunds')
