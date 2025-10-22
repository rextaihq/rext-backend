"""add_trial_conversions_table

Revision ID: 36df81bd9575
Revises: 2aa8488d9f4d
Create Date: 2025-10-18 19:28:41.923360

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '36df81bd9575'
down_revision: Union[str, Sequence[str], None] = '2aa8488d9f4d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create trial_conversions table
    op.create_table(
        'trial_conversions',
        sa.Column('id', sa.dialects.postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('user_id', sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('subscription_id', sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('trial_started_at', sa.TIMESTAMP(timezone=True), nullable=False, comment='When the trial started'),
        sa.Column('trial_ended_at', sa.TIMESTAMP(timezone=True), nullable=False, comment='When the trial ended'),
        sa.Column('converted_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False, comment='When trial converted to paid'),
        sa.Column('trial_duration_days', sa.Integer(), nullable=False, comment='Total trial duration in days'),
        sa.Column('conversion_plan_id', sa.dialects.postgresql.UUID(as_uuid=True), nullable=False, comment='Plan user converted to'),
        sa.Column('conversion_billing_period', sa.String(20), nullable=False, comment='Monthly or yearly'),
        sa.Column('conversion_amount', sa.Numeric(10, 2), nullable=True, comment='First payment amount'),
        sa.Column('conversion_metadata', sa.dialects.postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb"), comment='Additional conversion data'),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['subscription_id'], ['user_subscriptions.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['conversion_plan_id'], ['subscription_plans.id'], ondelete='SET NULL')
    )

    # Create indexes for analytics queries
    op.create_index('idx_trial_conversions_user_id', 'trial_conversions', ['user_id'])
    op.create_index('idx_trial_conversions_subscription_id', 'trial_conversions', ['subscription_id'])
    op.create_index('idx_trial_conversions_converted_at', 'trial_conversions', ['converted_at'])
    op.create_index('idx_trial_conversions_plan_id', 'trial_conversions', ['conversion_plan_id'])


def downgrade() -> None:
    """Downgrade schema."""
    # Drop indexes
    op.drop_index('idx_trial_conversions_plan_id', table_name='trial_conversions')
    op.drop_index('idx_trial_conversions_converted_at', table_name='trial_conversions')
    op.drop_index('idx_trial_conversions_subscription_id', table_name='trial_conversions')
    op.drop_index('idx_trial_conversions_user_id', table_name='trial_conversions')

    # Drop table
    op.drop_table('trial_conversions')
