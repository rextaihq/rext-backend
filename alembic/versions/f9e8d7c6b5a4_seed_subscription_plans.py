"""seed_subscription_plans

Revision ID: f9e8d7c6b5a4
Revises: a1f2e3d4c5b6
Create Date: 2025-10-02 18:30:00.000000

"""
from typing import Sequence, Union
from alembic import op
from sqlalchemy import orm
from sqlalchemy.ext.declarative import declarative_base
import sqlalchemy as sa
import uuid
from datetime import datetime
from decimal import Decimal

# revision identifiers, used by Alembic.
revision: str = 'f9e8d7c6b5a4'
down_revision: Union[str, Sequence[str], None] = 'a1f2e3d4c5b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

Base = declarative_base()


class SubscriptionPlan(Base):
    """Lightweight model for seeding subscription plans."""
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
    stripe_price_id_monthly = sa.Column(sa.String(255))
    stripe_price_id_yearly = sa.Column(sa.String(255))
    created_at = sa.Column(sa.TIMESTAMP, nullable=False)
    updated_at = sa.Column(sa.TIMESTAMP)


def upgrade() -> None:
    """Seed default subscription plans."""
    bind = op.get_bind()
    session = orm.Session(bind=bind)

    # Check if plans already exist (idempotent)
    existing_plans = session.query(SubscriptionPlan).filter(
        SubscriptionPlan.name.in_(['free', 'pro', 'enterprise'])
    ).count()

    if existing_plans > 0:
        print(f"Subscription plans already exist ({existing_plans} found). Skipping seed.")
        return

    # Define 3 default plans
    plans_data = [
        {
            "id": uuid.uuid4(),
            "name": "free",
            "display_name": "Free Plan",
            "description": "Perfect for individuals and small projects. Get started with essential features at no cost.",
            "price_monthly": Decimal("0.00"),
            "price_yearly": Decimal("0.00"),
            "features": {
                "collaboration": "Basic",
                "support": "Community",
                "api_access": "Limited",
                "custom_branding": False,
                "advanced_analytics": False,
                "priority_support": False
            },
            "max_workspaces": 1,
            "max_members_per_workspace": 3,
            "max_topics": 50,
            "max_knowledge_items": 100,
            "max_api_calls_per_month": 1000,
            "is_active": True,
            "is_public": True,
            "stripe_price_id_monthly": None,
            "stripe_price_id_yearly": None,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        },
        {
            "id": uuid.uuid4(),
            "name": "pro",
            "display_name": "Pro Plan",
            "description": "For growing teams that need more power and flexibility. Unlock advanced features and higher limits.",
            "price_monthly": Decimal("29.99"),
            "price_yearly": Decimal("299.99"),
            "features": {
                "collaboration": "Advanced",
                "support": "Email & Chat",
                "api_access": "Full",
                "custom_branding": True,
                "advanced_analytics": True,
                "priority_support": False
            },
            "max_workspaces": 5,
            "max_members_per_workspace": 10,
            "max_topics": 500,
            "max_knowledge_items": 5000,
            "max_api_calls_per_month": 50000,
            "is_active": True,
            "is_public": True,
            "stripe_price_id_monthly": None,  # To be configured when Stripe is integrated
            "stripe_price_id_yearly": None,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        },
        {
            "id": uuid.uuid4(),
            "name": "enterprise",
            "display_name": "Enterprise Plan",
            "description": "For large organizations with complex needs. Unlimited everything with dedicated support.",
            "price_monthly": Decimal("99.99"),
            "price_yearly": Decimal("999.99"),
            "features": {
                "collaboration": "Enterprise",
                "support": "24/7 Priority",
                "api_access": "Unlimited",
                "custom_branding": True,
                "advanced_analytics": True,
                "priority_support": True,
                "dedicated_account_manager": True,
                "custom_integrations": True,
                "sla_guarantee": True
            },
            "max_workspaces": -1,  # -1 = unlimited
            "max_members_per_workspace": -1,
            "max_topics": -1,
            "max_knowledge_items": -1,
            "max_api_calls_per_month": -1,
            "is_active": True,
            "is_public": True,
            "stripe_price_id_monthly": None,
            "stripe_price_id_yearly": None,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
    ]

    # Insert plans
    for plan_data in plans_data:
        plan = SubscriptionPlan(**plan_data)
        session.add(plan)

    session.commit()
    print(f"✅ Successfully seeded {len(plans_data)} subscription plans")


def downgrade() -> None:
    """Remove seeded subscription plans."""
    bind = op.get_bind()
    session = orm.Session(bind=bind)

    # Delete seeded plans
    session.query(SubscriptionPlan).filter(
        SubscriptionPlan.name.in_(['free', 'pro', 'enterprise'])
    ).delete(synchronize_session=False)

    session.commit()
    print("✅ Removed seeded subscription plans")
