"""add_grace_period_fields_to_subscriptions

Revision ID: 1318ededff9c
Revises: 36df81bd9575
Create Date: 2025-10-18 19:44:42.238826

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1318ededff9c'
down_revision: Union[str, Sequence[str], None] = '36df81bd9575'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add grace_period_end column to track when subscription should be suspended
    op.add_column(
        'user_subscriptions',
        sa.Column('grace_period_end', sa.DateTime(timezone=True), nullable=True)
    )

    # Add payment_failed_at column to track when payment first failed
    op.add_column(
        'user_subscriptions',
        sa.Column('payment_failed_at', sa.DateTime(timezone=True), nullable=True)
    )

    # Add index on grace_period_end for efficient background job queries
    op.create_index(
        'ix_user_subscriptions_grace_period_end',
        'user_subscriptions',
        ['grace_period_end'],
        unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Remove index
    op.drop_index('ix_user_subscriptions_grace_period_end', table_name='user_subscriptions')

    # Remove columns
    op.drop_column('user_subscriptions', 'payment_failed_at')
    op.drop_column('user_subscriptions', 'grace_period_end')
