"""add orders table

Local record of every LemonSqueezy purchase, so billing history, refunds and
entitlement checks stop depending on live LemonSqueezy API calls — and so an
arbitrary LemonSqueezy order id can be resolved back to a user.

Revision ID: ord20260903
Revises: 20260901ipallow
Create Date: 2026-09-03

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM, UUID


# revision identifiers, used by Alembic.
revision: str = 'ord20260903'
down_revision: Union[str, Sequence[str], None] = '20260907emailresend'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


ORDER_STATUSES = ('pending', 'paid', 'failed', 'refunded', 'partial_refund')


def upgrade() -> None:
    """Create the orders table and its status enum."""
    # Create the type once, explicitly. create_type=False on the column stops
    # create_table from emitting a second CREATE TYPE for the same name.
    ENUM(*ORDER_STATUSES, name='orderstatus').create(op.get_bind(), checkfirst=True)
    order_status = ENUM(*ORDER_STATUSES, name='orderstatus', create_type=False)

    op.create_table(
        'orders',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('user_id', UUID(as_uuid=True), nullable=False),
        sa.Column('subscription_id', UUID(as_uuid=True), nullable=True),

        # LemonSqueezy identifiers
        sa.Column('lemonsqueezy_order_id', sa.String(255), nullable=False),
        sa.Column('lemonsqueezy_customer_id', sa.String(255), nullable=True),
        sa.Column('lemonsqueezy_subscription_id', sa.String(255), nullable=True),
        sa.Column('lemonsqueezy_product_id', sa.String(255), nullable=True),
        sa.Column('lemonsqueezy_variant_id', sa.String(255), nullable=True),

        # Order details. Amounts in cents, matching LemonSqueezy and refunds.
        sa.Column('product_name', sa.String(255), nullable=True),
        sa.Column('total', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('subtotal', sa.Integer(), nullable=True),
        sa.Column('tax', sa.Integer(), nullable=True),
        sa.Column('currency', sa.String(3), nullable=False, server_default='USD'),
        sa.Column('status', order_status, nullable=False, server_default='pending'),
        sa.Column('receipt_url', sa.String(1024), nullable=True),

        # Timestamps
        sa.Column('refunded_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('ordered_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('CURRENT_TIMESTAMP')),

        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['subscription_id'], ['user_subscriptions.id'], ondelete='SET NULL'),
    )

    # Unique so webhook retries upsert rather than duplicate.
    op.create_index('ix_orders_lemonsqueezy_order_id', 'orders',
                    ['lemonsqueezy_order_id'], unique=True)
    op.create_index('ix_orders_user_id', 'orders', ['user_id'])
    op.create_index('ix_orders_subscription_id', 'orders', ['subscription_id'])
    op.create_index('ix_orders_lemonsqueezy_customer_id', 'orders',
                    ['lemonsqueezy_customer_id'])
    op.create_index('ix_orders_lemonsqueezy_subscription_id', 'orders',
                    ['lemonsqueezy_subscription_id'])
    op.create_index('ix_orders_lemonsqueezy_variant_id', 'orders',
                    ['lemonsqueezy_variant_id'])
    op.create_index('ix_orders_status', 'orders', ['status'])
    op.create_index('ix_orders_ordered_at', 'orders', ['ordered_at'])


def downgrade() -> None:
    """Drop the orders table and its status enum."""
    op.drop_index('ix_orders_ordered_at', table_name='orders')
    op.drop_index('ix_orders_status', table_name='orders')
    op.drop_index('ix_orders_lemonsqueezy_variant_id', table_name='orders')
    op.drop_index('ix_orders_lemonsqueezy_subscription_id', table_name='orders')
    op.drop_index('ix_orders_lemonsqueezy_customer_id', table_name='orders')
    op.drop_index('ix_orders_subscription_id', table_name='orders')
    op.drop_index('ix_orders_user_id', table_name='orders')
    op.drop_index('ix_orders_lemonsqueezy_order_id', table_name='orders')
    op.drop_table('orders')
    sa.Enum(name='orderstatus').drop(op.get_bind(), checkfirst=True)
