"""rename_stripe_fields_to_provider_agnostic

Revision ID: 2f08b3178c5d
Revises: 971d7fde2ea5
Create Date: 2025-10-12 21:06:42.059827

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2f08b3178c5d'
down_revision: Union[str, Sequence[str], None] = '971d7fde2ea5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Rename Stripe-specific fields to provider-agnostic names."""
    # Rename fields in subscription_plans table
    op.alter_column(
        'subscription_plans',
        'stripe_price_id_monthly',
        new_column_name='provider_price_id_monthly'
    )
    op.alter_column(
        'subscription_plans',
        'stripe_price_id_yearly',
        new_column_name='provider_price_id_yearly'
    )

    # Rename fields in user_subscriptions table
    op.alter_column(
        'user_subscriptions',
        'stripe_subscription_id',
        new_column_name='provider_subscription_id'
    )
    op.alter_column(
        'user_subscriptions',
        'stripe_customer_id',
        new_column_name='provider_customer_id'
    )


def downgrade() -> None:
    """Revert provider-agnostic fields back to Stripe-specific names."""
    # Revert fields in subscription_plans table
    op.alter_column(
        'subscription_plans',
        'provider_price_id_monthly',
        new_column_name='stripe_price_id_monthly'
    )
    op.alter_column(
        'subscription_plans',
        'provider_price_id_yearly',
        new_column_name='stripe_price_id_yearly'
    )

    # Revert fields in user_subscriptions table
    op.alter_column(
        'user_subscriptions',
        'provider_subscription_id',
        new_column_name='stripe_subscription_id'
    )
    op.alter_column(
        'user_subscriptions',
        'provider_customer_id',
        new_column_name='stripe_customer_id'
    )
