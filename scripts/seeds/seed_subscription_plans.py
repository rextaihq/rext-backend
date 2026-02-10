"""Seed default subscription plans."""

import asyncio
from decimal import Decimal
from sqlalchemy import text
from uuid import uuid4

from scripts.seeds.base import get_seed_session, utc_now

PLANS = [
    {
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
        "is_public": True
    },
    {
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
        "is_public": True
    },
    {
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
        "is_public": True
    }
]

async def seed_subscription_plans():
    """Seed subscription plans (idempotent — skips existing by name)."""
    async with get_seed_session() as session:
        created = 0
        skipped = 0

        for plan in PLANS:
            result = await session.execute(
                text("SELECT id FROM subscription_plans WHERE name = :name"),
                {"name": plan["name"]}
            )
            if result.fetchone():
                skipped += 1
                continue

            await session.execute(
                text("""
                    INSERT INTO subscription_plans (
                        id, name, display_name, description, price_monthly, price_yearly, 
                        features, max_workspaces, max_members_per_workspace, max_topics, 
                        max_knowledge_items, max_api_calls_per_month, is_active, is_public, 
                        created_at, updated_at
                    ) VALUES (
                        :id, :name, :display_name, :description, :price_monthly, :price_yearly, 
                        :features, :max_workspaces, :max_members_per_workspace, :max_topics, 
                        :max_knowledge_items, :max_api_calls_per_month, :is_active, :is_public, 
                        :created_at, :updated_at
                    )
                """),
                {
                    "id": uuid4(),
                    "name": plan["name"],
                    "display_name": plan["display_name"],
                    "description": plan["description"],
                    "price_monthly": plan["price_monthly"],
                    "price_yearly": plan["price_yearly"],
                    "features": plan["features"], # SQLAlchemy handles JSONB conversion if using JSONB type
                    "max_workspaces": plan["max_workspaces"],
                    "max_members_per_workspace": plan["max_members_per_workspace"],
                    "max_topics": plan["max_topics"],
                    "max_knowledge_items": plan["max_knowledge_items"],
                    "max_api_calls_per_month": plan["max_api_calls_per_month"],
                    "is_active": plan["is_active"],
                    "is_public": plan["is_public"],
                    "created_at": utc_now(),
                    "updated_at": utc_now(),
                }
            )
            created += 1

        print(f"Subscription plans: {created} created, {skipped} already existed")

if __name__ == "__main__":
    asyncio.run(seed_subscription_plans())
