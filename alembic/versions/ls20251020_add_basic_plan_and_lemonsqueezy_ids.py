"""add_basic_plan_and_lemonsqueezy_ids

Revision ID: ls20251020
Revises: rem20251020
Create Date: 2025-10-20 21:00:00.000000

This migration:
1. Adds a new 'basic' plan between free and pro
2. Updates existing plans with LemonSqueezy product/variant IDs
3. Fixes Pro plan yearly price to match LemonSqueezy ($290.99)
"""
from typing import Sequence, Union
from alembic import op
from sqlalchemy import orm, text
from sqlalchemy.ext.declarative import declarative_base
import sqlalchemy as sa
import uuid
from datetime import datetime
from decimal import Decimal

# revision identifiers, used by Alembic.
revision: str = 'ls20251020'
down_revision: Union[str, Sequence[str], None] = 'rem20251020'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

Base = declarative_base()


class SubscriptionPlan(Base):
    """Lightweight model for updating subscription plans."""
    __tablename__ = 'subscription_plans'

    id = sa.Column(sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True)
    name = sa.Column(sa.String(100), unique=True, nullable=False)
    display_name = sa.Column(sa.String(150), nullable=False)
    description = sa.Column(sa.Text)
    price_monthly = sa.Column(sa.Numeric(10, 2))
    price_yearly = sa.Column(sa.Numeric(10, 2))
    features = sa.Column(sa.dialects.postgresql.JSONB)
    max_workspaces = sa.Column(sa.Integer)
    max_members_per_workspace = sa.Column(sa.Integer)
    max_topics = sa.Column(sa.Integer)
    max_knowledge_items = sa.Column(sa.Integer)
    max_api_calls_per_month = sa.Column(sa.Integer)
    is_active = sa.Column(sa.Boolean, default=True)
    is_public = sa.Column(sa.Boolean, default=True)
    provider_price_id_monthly = sa.Column(sa.String(255))
    provider_price_id_yearly = sa.Column(sa.String(255))
    lemonsqueezy_product_id = sa.Column(sa.String(255))
    lemonsqueezy_variant_id_monthly = sa.Column(sa.String(255))
    lemonsqueezy_variant_id_yearly = sa.Column(sa.String(255))
    lemonsqueezy_store_id = sa.Column(sa.String(255))
    created_at = sa.Column(sa.TIMESTAMP, nullable=False)
    updated_at = sa.Column(sa.TIMESTAMP)


def upgrade() -> None:
    """Add basic plan and update LemonSqueezy IDs."""
    bind = op.get_bind()
    session = orm.Session(bind=bind)

    # LemonSqueezy Store ID (from .env)
    LEMONSQUEEZY_STORE_ID = "230544"

    # Step 1: Check if basic plan already exists
    existing_basic = session.query(SubscriptionPlan).filter(
        SubscriptionPlan.name == 'basic'
    ).first()

    if not existing_basic:
        print("Creating 'basic' plan...")

        # Create basic plan (entry-level paid tier)
        basic_plan = SubscriptionPlan(
            id=uuid.uuid4(),
            name="basic",
            display_name="Basic Plan",
            description="Perfect for individuals and small teams. Get started with essential features at an affordable price.",
            price_monthly=Decimal("9.99"),
            price_yearly=Decimal("99.99"),
            features={
                "collaboration": "Basic",
                "support": "Email Support",
                "api_access": "Standard",
                "custom_branding": False,
                "advanced_analytics": False,
                "priority_support": False
            },
            max_workspaces=1,
            max_members_per_workspace=5,
            max_topics=100,
            max_knowledge_items=500,
            max_api_calls_per_month=5000,
            is_active=True,
            is_public=True,
            # LemonSqueezy Basic Plan IDs
            lemonsqueezy_product_id="665157",
            lemonsqueezy_variant_id_monthly="1045158",
            lemonsqueezy_variant_id_yearly="1049347",
            lemonsqueezy_store_id=LEMONSQUEEZY_STORE_ID,
            provider_price_id_monthly="1045158",  # Variant ID for generic provider field
            provider_price_id_yearly="1049347",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        session.add(basic_plan)
        print("✅ Created 'basic' plan")
    else:
        print("'basic' plan already exists, skipping creation")

    # Step 2: Update Free plan (keep at $0, no LemonSqueezy integration)
    free_plan = session.query(SubscriptionPlan).filter(
        SubscriptionPlan.name == 'free'
    ).first()

    if free_plan:
        print("Updating 'free' plan...")
        free_plan.description = "Free tier for individuals. Get started with basic features at no cost."
        free_plan.max_members_per_workspace = 3
        free_plan.max_topics = 50
        free_plan.max_knowledge_items = 100
        free_plan.max_api_calls_per_month = 1000
        # Free plan has NO LemonSqueezy integration (handled in-app only)
        free_plan.lemonsqueezy_product_id = None
        free_plan.lemonsqueezy_variant_id_monthly = None
        free_plan.lemonsqueezy_variant_id_yearly = None
        free_plan.lemonsqueezy_store_id = None
        free_plan.provider_price_id_monthly = None
        free_plan.provider_price_id_yearly = None
        free_plan.updated_at = datetime.utcnow()
        print("✅ Updated 'free' plan")

    # Step 3: Update Pro plan with LemonSqueezy IDs and fix yearly price
    pro_plan = session.query(SubscriptionPlan).filter(
        SubscriptionPlan.name == 'pro'
    ).first()

    if pro_plan:
        print("Updating 'pro' plan with LemonSqueezy IDs...")
        pro_plan.price_yearly = Decimal("290.99")  # Fix: was $299.99, should be $290.99
        pro_plan.max_members_per_workspace = 15
        pro_plan.max_topics = 500
        pro_plan.max_knowledge_items = 5000
        pro_plan.max_api_calls_per_month = 50000
        # LemonSqueezy Pro Plan IDs
        pro_plan.lemonsqueezy_product_id = "667795"
        pro_plan.lemonsqueezy_variant_id_monthly = "1049346"
        pro_plan.lemonsqueezy_variant_id_yearly = "1049351"
        pro_plan.lemonsqueezy_store_id = LEMONSQUEEZY_STORE_ID
        pro_plan.provider_price_id_monthly = "1049346"  # Variant ID for generic provider field
        pro_plan.provider_price_id_yearly = "1049351"
        pro_plan.updated_at = datetime.utcnow()
        print("✅ Updated 'pro' plan (fixed yearly price: $299.99 → $290.99)")

    # Step 4: Update Enterprise plan (no LemonSqueezy for now - custom pricing)
    enterprise_plan = session.query(SubscriptionPlan).filter(
        SubscriptionPlan.name == 'enterprise'
    ).first()

    if enterprise_plan:
        print("Updating 'enterprise' plan...")
        enterprise_plan.description = "For large organizations with complex needs. Contact us for custom pricing and dedicated support."
        enterprise_plan.is_public = False  # Hide from pricing page - contact sales only
        # Enterprise: no LemonSqueezy integration yet (custom contracts)
        enterprise_plan.lemonsqueezy_product_id = None
        enterprise_plan.lemonsqueezy_variant_id_monthly = None
        enterprise_plan.lemonsqueezy_variant_id_yearly = None
        enterprise_plan.lemonsqueezy_store_id = None
        enterprise_plan.provider_price_id_monthly = None
        enterprise_plan.provider_price_id_yearly = None
        enterprise_plan.updated_at = datetime.utcnow()
        print("✅ Updated 'enterprise' plan (marked as not public - contact sales)")

    session.commit()

    print("\n" + "="*70)
    print("✅ Migration complete!")
    print("="*70)
    print("\nPlan Summary:")
    print("-" * 70)

    plans = session.query(SubscriptionPlan).order_by(SubscriptionPlan.price_monthly).all()
    for plan in plans:
        print(f"\n{plan.display_name} ({plan.name}):")
        print(f"  Price: ${plan.price_monthly}/mo | ${plan.price_yearly}/yr")
        print(f"  LemonSqueezy Product ID: {plan.lemonsqueezy_product_id or 'N/A'}")
        print(f"  Variant Monthly: {plan.lemonsqueezy_variant_id_monthly or 'N/A'}")
        print(f"  Variant Yearly: {plan.lemonsqueezy_variant_id_yearly or 'N/A'}")
        print(f"  Public: {'Yes' if plan.is_public else 'No (Contact Sales)'}")


def downgrade() -> None:
    """Rollback: Remove basic plan and clear LemonSqueezy IDs."""
    bind = op.get_bind()
    session = orm.Session(bind=bind)

    print("Rolling back migration...")

    # Remove basic plan
    session.query(SubscriptionPlan).filter(
        SubscriptionPlan.name == 'basic'
    ).delete(synchronize_session=False)
    print("✅ Removed 'basic' plan")

    # Clear LemonSqueezy IDs from all plans
    session.execute(
        text("""
            UPDATE subscription_plans
            SET
                lemonsqueezy_product_id = NULL,
                lemonsqueezy_variant_id_monthly = NULL,
                lemonsqueezy_variant_id_yearly = NULL,
                lemonsqueezy_store_id = NULL,
                provider_price_id_monthly = NULL,
                provider_price_id_yearly = NULL,
                updated_at = NOW()
            WHERE name IN ('pro', 'free', 'enterprise')
        """)
    )
    print("✅ Cleared LemonSqueezy IDs from existing plans")

    # Restore Pro plan yearly price to $299.99
    pro_plan = session.query(SubscriptionPlan).filter(
        SubscriptionPlan.name == 'pro'
    ).first()
    if pro_plan:
        pro_plan.price_yearly = Decimal("299.99")
        print("✅ Restored Pro plan yearly price to $299.99")

    # Restore Enterprise to public
    enterprise_plan = session.query(SubscriptionPlan).filter(
        SubscriptionPlan.name == 'enterprise'
    ).first()
    if enterprise_plan:
        enterprise_plan.is_public = True
        print("✅ Restored Enterprise plan to public")

    session.commit()
    print("✅ Migration rolled back successfully")
