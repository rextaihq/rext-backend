"""add_lemonsqueezy_integration

Revision ID: 33eb548e7bd9
Revises: 40fd95ca1e8d
Create Date: 2025-10-17 14:02:25.980750

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB


# revision identifiers, used by Alembic.
revision: str = '33eb548e7bd9'
down_revision: Union[str, Sequence[str], None] = '40fd95ca1e8d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema to support LemonSqueezy integration.

    This migration adds:
    1. LemonSqueezy-specific fields to subscription_plans table
    2. LemonSqueezy-specific fields to user_subscriptions table
    3. New webhook_events table for idempotency tracking
    4. New licenses table for one-time purchase license keys
    5. Extended SubscriptionStatus enum with PAST_DUE and PAUSED
    """

    # ========================================
    # 1. Update subscription_plans table
    # ========================================
    op.add_column('subscription_plans', sa.Column('lemonsqueezy_product_id', sa.String(255), nullable=True))
    op.add_column('subscription_plans', sa.Column('lemonsqueezy_variant_id_monthly', sa.String(255), nullable=True))
    op.add_column('subscription_plans', sa.Column('lemonsqueezy_variant_id_yearly', sa.String(255), nullable=True))
    op.add_column('subscription_plans', sa.Column('lemonsqueezy_store_id', sa.String(255), nullable=True))

    # Create indexes for LemonSqueezy IDs (for faster lookups)
    op.create_index('ix_subscription_plans_lemonsqueezy_product_id', 'subscription_plans', ['lemonsqueezy_product_id'])
    op.create_index('ix_subscription_plans_lemonsqueezy_variant_monthly', 'subscription_plans', ['lemonsqueezy_variant_id_monthly'])
    op.create_index('ix_subscription_plans_lemonsqueezy_variant_yearly', 'subscription_plans', ['lemonsqueezy_variant_id_yearly'])

    # ========================================
    # 2. Update user_subscriptions table
    # ========================================
    op.add_column('user_subscriptions', sa.Column('lemonsqueezy_subscription_id', sa.String(255), nullable=True))
    op.add_column('user_subscriptions', sa.Column('lemonsqueezy_customer_id', sa.String(255), nullable=True))
    op.add_column('user_subscriptions', sa.Column('lemonsqueezy_order_id', sa.String(255), nullable=True))
    op.add_column('user_subscriptions', sa.Column('lemonsqueezy_product_id', sa.String(255), nullable=True))
    op.add_column('user_subscriptions', sa.Column('lemonsqueezy_variant_id', sa.String(255), nullable=True))
    op.add_column('user_subscriptions', sa.Column('renews_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('user_subscriptions', sa.Column('ends_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('user_subscriptions', sa.Column('cancel_at_period_end', sa.Boolean(), default=False, nullable=False, server_default='false'))

    # Create indexes for LemonSqueezy IDs
    op.create_index('ix_user_subscriptions_lemonsqueezy_subscription_id', 'user_subscriptions', ['lemonsqueezy_subscription_id'], unique=True)
    op.create_index('ix_user_subscriptions_lemonsqueezy_customer_id', 'user_subscriptions', ['lemonsqueezy_customer_id'])
    op.create_index('ix_user_subscriptions_renews_at', 'user_subscriptions', ['renews_at'])

    # ========================================
    # 3. Extend SubscriptionStatus enum
    # ========================================
    # Add new enum values for LemonSqueezy subscription statuses
    op.execute("ALTER TYPE subscriptionstatus ADD VALUE IF NOT EXISTS 'past_due'")
    op.execute("ALTER TYPE subscriptionstatus ADD VALUE IF NOT EXISTS 'paused'")

    # ========================================
    # 4. Create webhook_events table
    # ========================================
    op.create_table(
        'webhook_events',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('event_id', sa.String(255), nullable=False),
        sa.Column('event_name', sa.String(100), nullable=False),
        sa.Column('payload', JSONB, nullable=False),
        sa.Column('processed', sa.Boolean(), default=False, nullable=False),
        sa.Column('processed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('retry_count', sa.Integer(), default=0, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()'))
    )

    # Create indexes for webhook_events
    op.create_index('ix_webhook_events_event_id', 'webhook_events', ['event_id'], unique=True)
    op.create_index('ix_webhook_events_event_name', 'webhook_events', ['event_name'])
    op.create_index('ix_webhook_events_processed', 'webhook_events', ['processed'])
    op.create_index('ix_webhook_events_created_at', 'webhook_events', ['created_at'])

    # ========================================
    # 5. Create licenses table
    # ========================================
    # Create enum for license status (check if exists first)
    # Using raw SQL to avoid SQLAlchemy attempting to create the type
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE licensestatus AS ENUM ('active', 'inactive', 'expired', 'disabled');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)

    # Use raw SQL to create table to avoid SQLAlchemy enum creation issues
    op.execute("""
        CREATE TABLE IF NOT EXISTS licenses (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID REFERENCES users(id) ON DELETE SET NULL,
            license_key VARCHAR(255) NOT NULL,
            lemonsqueezy_license_id VARCHAR(255) NOT NULL,
            lemonsqueezy_order_id VARCHAR(255) NOT NULL,
            lemonsqueezy_product_id VARCHAR(255) NOT NULL,
            product_name VARCHAR(255) NOT NULL,
            status licensestatus NOT NULL DEFAULT 'inactive'::licensestatus,
            activation_email VARCHAR(255) NOT NULL,
            activation_limit INTEGER,
            activation_count INTEGER NOT NULL DEFAULT 0,
            activated_at TIMESTAMP,
            expires_at TIMESTAMP,
            license_metadata JSONB NOT NULL DEFAULT '{}',
            created_at TIMESTAMP NOT NULL DEFAULT now(),
            updated_at TIMESTAMP NOT NULL DEFAULT now()
        )
    """)

    # Create indexes for licenses
    op.create_index('ix_licenses_license_key', 'licenses', ['license_key'], unique=True)
    op.create_index('ix_licenses_lemonsqueezy_license_id', 'licenses', ['lemonsqueezy_license_id'], unique=True)
    op.create_index('ix_licenses_user_id', 'licenses', ['user_id'])
    op.create_index('ix_licenses_activation_email', 'licenses', ['activation_email'])
    op.create_index('ix_licenses_status', 'licenses', ['status'])


def downgrade() -> None:
    """Downgrade schema - remove LemonSqueezy integration.

    WARNING: This will drop the webhook_events and licenses tables,
    losing all webhook history and license data.
    """

    # ========================================
    # 1. Drop licenses table and enum
    # ========================================
    op.drop_index('ix_licenses_status', table_name='licenses')
    op.drop_index('ix_licenses_activation_email', table_name='licenses')
    op.drop_index('ix_licenses_user_id', table_name='licenses')
    op.drop_index('ix_licenses_lemonsqueezy_license_id', table_name='licenses')
    op.drop_index('ix_licenses_license_key', table_name='licenses')
    op.drop_table('licenses')
    op.execute('DROP TYPE licensestatus')

    # ========================================
    # 2. Drop webhook_events table
    # ========================================
    op.drop_index('ix_webhook_events_created_at', table_name='webhook_events')
    op.drop_index('ix_webhook_events_processed', table_name='webhook_events')
    op.drop_index('ix_webhook_events_event_name', table_name='webhook_events')
    op.drop_index('ix_webhook_events_event_id', table_name='webhook_events')
    op.drop_table('webhook_events')

    # ========================================
    # 3. Remove enum values from SubscriptionStatus
    # ========================================
    # NOTE: PostgreSQL does not support removing enum values directly.
    # In production, you would need to:
    # 1. Create a new enum without the values
    # 2. Alter columns to use the new enum
    # 3. Drop the old enum
    # For this migration, we'll leave the enum values (safe, as they're unused after downgrade)

    # ========================================
    # 4. Remove columns from user_subscriptions
    # ========================================
    op.drop_index('ix_user_subscriptions_renews_at', table_name='user_subscriptions')
    op.drop_index('ix_user_subscriptions_lemonsqueezy_customer_id', table_name='user_subscriptions')
    op.drop_index('ix_user_subscriptions_lemonsqueezy_subscription_id', table_name='user_subscriptions')
    op.drop_column('user_subscriptions', 'cancel_at_period_end')
    op.drop_column('user_subscriptions', 'ends_at')
    op.drop_column('user_subscriptions', 'renews_at')
    op.drop_column('user_subscriptions', 'lemonsqueezy_variant_id')
    op.drop_column('user_subscriptions', 'lemonsqueezy_product_id')
    op.drop_column('user_subscriptions', 'lemonsqueezy_order_id')
    op.drop_column('user_subscriptions', 'lemonsqueezy_customer_id')
    op.drop_column('user_subscriptions', 'lemonsqueezy_subscription_id')

    # ========================================
    # 5. Remove columns from subscription_plans
    # ========================================
    op.drop_index('ix_subscription_plans_lemonsqueezy_variant_yearly', table_name='subscription_plans')
    op.drop_index('ix_subscription_plans_lemonsqueezy_variant_monthly', table_name='subscription_plans')
    op.drop_index('ix_subscription_plans_lemonsqueezy_product_id', table_name='subscription_plans')
    op.drop_column('subscription_plans', 'lemonsqueezy_store_id')
    op.drop_column('subscription_plans', 'lemonsqueezy_variant_id_yearly')
    op.drop_column('subscription_plans', 'lemonsqueezy_variant_id_monthly')
    op.drop_column('subscription_plans', 'lemonsqueezy_product_id')
