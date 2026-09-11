"""add refund_requests table

Customer-initiated refund requests, kept separate from `refunds` so that
requests and rejections never count toward refunded money in reporting, and so
a pending request cannot trip the "refund already exists" guard.

Revision ID: rr20260903
Revises: ord20260903
Create Date: 2026-09-03

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ENUM, UUID


# revision identifiers, used by Alembic.
revision: str = 'rr20260903'
down_revision: Union[str, Sequence[str], None] = 'ord20260903'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


REQUEST_STATUSES = ('pending', 'approved', 'rejected')


def upgrade() -> None:
    """Create the refund_requests table and its status enum."""
    # Created once explicitly; create_type=False stops create_table emitting a
    # second CREATE TYPE for the same name.
    ENUM(*REQUEST_STATUSES, name='refundrequeststatus').create(
        op.get_bind(), checkfirst=True
    )
    request_status = ENUM(
        *REQUEST_STATUSES, name='refundrequeststatus', create_type=False
    )

    op.create_table(
        'refund_requests',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('user_id', UUID(as_uuid=True), nullable=False),
        sa.Column('order_id', UUID(as_uuid=True), nullable=False),
        sa.Column('lemonsqueezy_order_id', sa.String(255), nullable=False),

        sa.Column('requested_amount', sa.Integer(), nullable=False),
        sa.Column('currency', sa.String(3), nullable=False, server_default='USD'),
        sa.Column('reason', sa.Text(), nullable=False),

        sa.Column('status', request_status, nullable=False, server_default='pending'),
        sa.Column('reviewed_by_user_id', UUID(as_uuid=True), nullable=True),
        sa.Column('admin_note', sa.Text(), nullable=True),
        sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('refund_id', UUID(as_uuid=True), nullable=True),

        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text('CURRENT_TIMESTAMP')),

        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['order_id'], ['orders.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['reviewed_by_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['refund_id'], ['refunds.id'], ondelete='SET NULL'),
    )

    op.create_index('ix_refund_requests_user_id', 'refund_requests', ['user_id'])
    op.create_index('ix_refund_requests_order_id', 'refund_requests', ['order_id'])
    op.create_index('ix_refund_requests_ls_order_id', 'refund_requests',
                    ['lemonsqueezy_order_id'])
    op.create_index('ix_refund_requests_status', 'refund_requests', ['status'])
    op.create_index('ix_refund_requests_created_at', 'refund_requests', ['created_at'])

    # At most one open request per order, so a customer cannot queue duplicates
    # and admins never see the same order twice in the review list.
    op.create_index(
        'uq_refund_requests_one_open_per_order',
        'refund_requests',
        ['order_id'],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )


def downgrade() -> None:
    """Drop the refund_requests table and its status enum."""
    op.drop_index('uq_refund_requests_one_open_per_order', table_name='refund_requests')
    op.drop_index('ix_refund_requests_created_at', table_name='refund_requests')
    op.drop_index('ix_refund_requests_status', table_name='refund_requests')
    op.drop_index('ix_refund_requests_ls_order_id', table_name='refund_requests')
    op.drop_index('ix_refund_requests_order_id', table_name='refund_requests')
    op.drop_index('ix_refund_requests_user_id', table_name='refund_requests')
    op.drop_table('refund_requests')
    sa.Enum(name='refundrequeststatus').drop(op.get_bind(), checkfirst=True)
