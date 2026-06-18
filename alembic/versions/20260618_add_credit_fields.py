"""add_credit_fields

Revision ID: 20260618coupons
Revises: c1d2e3f4a5b6
Create Date: 2026-06-18

Adds credit-based billing columns to subscription_plans and user_subscriptions.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = '20260618coupons'
down_revision: Union[str, Sequence[str], None] = 'c1d2e3f4a5b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # subscription_plans — credit billing fields
    op.add_column('subscription_plans', sa.Column('credits_per_month', sa.Integer(), nullable=True))
    op.add_column('subscription_plans', sa.Column('is_trial_plan', sa.Boolean(), nullable=False, server_default='false'))

    # user_subscriptions — credit tracking
    op.add_column('user_subscriptions', sa.Column('current_credits', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('user_subscriptions', sa.Column('credits_reset_date', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('user_subscriptions', 'credits_reset_date')
    op.drop_column('user_subscriptions', 'current_credits')
    op.drop_column('subscription_plans', 'is_trial_plan')
    op.drop_column('subscription_plans', 'credits_per_month')
