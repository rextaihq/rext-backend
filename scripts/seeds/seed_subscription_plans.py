"""Seed the subscription plans: insert the ones missing, never change an existing one.

The values are the ones the migrations seeded before they were squashed into the
baseline (2026-10-05), so a new database starts where stage and live started.
Plans are changed in the admin or by a migration of their own, never here: this
seed runs on every environment.
"""

import asyncio
import json
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import text

from scripts.seeds.base import get_seed_session, utc_now

PLANS = [
    {
        "name": "trial",
        "display_name": "Trial",
        "description": "7-day free trial. Test the full pipeline before committing.",
        "price_monthly": Decimal("0.00"),
        "price_yearly": Decimal("0.00"),
        "credits_per_month": 60,
        "is_trial_plan": True,
        "features": None,
        "max_workspaces": 1,
        "max_members_per_workspace": 3,
        "max_api_calls_per_month": 100,
        "is_active": True,
        "is_public": False,
        "provider_price_id_monthly": None,
        "provider_price_id_yearly": None,
        "lemonsqueezy_store_id": None,
        "lemonsqueezy_product_id": None,
        "lemonsqueezy_variant_id_monthly": None,
        "lemonsqueezy_variant_id_yearly": None,
    },
    {
        "name": "starter",
        "display_name": "Starter",
        "description": "For freelancers and solo site owners.",
        "price_monthly": Decimal("39.00"),
        "price_yearly": Decimal("390.00"),
        "credits_per_month": 400,
        "is_trial_plan": False,
        "features": {
            "support": "Email Support",
            "api_access": "Standard",
            "collaboration": "Basic",
            "custom_branding": False,
            "priority_support": False,
            "advanced_analytics": False,
        },
        "max_workspaces": 1,
        "max_members_per_workspace": 5,
        "max_api_calls_per_month": 5000,
        "is_active": True,
        "is_public": True,
        "provider_price_id_monthly": "1049347",
        "provider_price_id_yearly": "1045158",
        "lemonsqueezy_store_id": "230544",
        "lemonsqueezy_product_id": "941169",
        "lemonsqueezy_variant_id_monthly": "1045158",
        "lemonsqueezy_variant_id_yearly": "1049350",
    },
    {
        "name": "growth",
        "display_name": "Growth",
        "description": "For small teams — most popular plan.",
        "price_monthly": Decimal("89.00"),
        "price_yearly": Decimal("890.00"),
        "credits_per_month": 1000,
        "is_trial_plan": False,
        "features": None,
        "max_workspaces": 3,
        "max_members_per_workspace": 10,
        "max_api_calls_per_month": 20000,
        "is_active": True,
        "is_public": True,
        "provider_price_id_monthly": None,
        "provider_price_id_yearly": None,
        "lemonsqueezy_store_id": "230544",
        "lemonsqueezy_product_id": "1227486",
        "lemonsqueezy_variant_id_monthly": "1798598",
        "lemonsqueezy_variant_id_yearly": "1798562",
    },
    {
        "name": "pro",
        "display_name": "Pro",
        "description": "For serious SEO teams that need API access.",
        "price_monthly": Decimal("189.00"),
        "price_yearly": Decimal("1890.00"),
        "credits_per_month": 2400,
        "is_trial_plan": False,
        "features": {
            "support": "Email & Chat",
            "api_access": "Full",
            "collaboration": "Advanced",
            "custom_branding": True,
            "priority_support": False,
            "advanced_analytics": True,
        },
        "max_workspaces": 5,
        "max_members_per_workspace": 15,
        "max_api_calls_per_month": 50000,
        "is_active": True,
        "is_public": True,
        "provider_price_id_monthly": "1049346",
        "provider_price_id_yearly": "1049351",
        "lemonsqueezy_store_id": "230544",
        "lemonsqueezy_product_id": "941200",
        "lemonsqueezy_variant_id_monthly": "1049346",
        "lemonsqueezy_variant_id_yearly": "1049352",
    },
    {
        "name": "agency",
        "display_name": "Agency",
        "description": "For agencies and white-label resellers.",
        "price_monthly": Decimal("399.00"),
        "price_yearly": Decimal("3990.00"),
        "credits_per_month": 5500,
        "is_trial_plan": False,
        "features": None,
        "max_workspaces": -1,
        "max_members_per_workspace": -1,
        "max_api_calls_per_month": -1,
        "is_active": True,
        "is_public": True,
        "provider_price_id_monthly": None,
        "provider_price_id_yearly": None,
        "lemonsqueezy_store_id": "230544",
        "lemonsqueezy_product_id": "1227456",
        "lemonsqueezy_variant_id_monthly": "1798564",
        "lemonsqueezy_variant_id_yearly": "1798605",
    },
    {
        "name": "enterprise",
        "display_name": "Enterprise",
        "description": "Custom credits, SSO, SLA, dedicated support.",
        "price_monthly": Decimal("999.00"),
        "price_yearly": Decimal("9990.00"),
        "credits_per_month": None,
        "is_trial_plan": False,
        "features": {
            "support": "24/7 Priority",
            "api_access": "Unlimited",
            "collaboration": "Enterprise",
            "sla_guarantee": True,
            "custom_branding": True,
            "priority_support": True,
            "advanced_analytics": True,
            "custom_integrations": True,
            "dedicated_account_manager": True,
        },
        "max_workspaces": -1,
        "max_members_per_workspace": -1,
        "max_api_calls_per_month": -1,
        "is_active": True,
        "is_public": False,
        "provider_price_id_monthly": None,
        "provider_price_id_yearly": None,
        "lemonsqueezy_store_id": None,
        "lemonsqueezy_product_id": None,
        "lemonsqueezy_variant_id_monthly": None,
        "lemonsqueezy_variant_id_yearly": None,
    },
]

COLUMNS = list(PLANS[0])


async def seed_subscription_plans():
    """Insert the plans that do not exist yet (by name)."""
    async with get_seed_session() as session:
        created = 0
        for plan in PLANS:
            exists = await session.scalar(
                text("SELECT 1 FROM subscription_plans WHERE name = :name"), {"name": plan["name"]}
            )
            if exists:
                continue
            features = plan["features"]
            values = {**plan, "features": None if features is None else json.dumps(features)}
            await session.execute(
                text(
                    f"INSERT INTO subscription_plans (id, {', '.join(COLUMNS)}, created_at, updated_at) "
                    f"VALUES (:id, {', '.join(f'CAST(:{c} AS JSONB)' if c == 'features' else f':{c}' for c in COLUMNS)}, "
                    ":created_at, :updated_at)"
                ),
                {**values, "id": uuid4(), "created_at": utc_now(), "updated_at": utc_now()},
            )
            created += 1
        print(f"Subscription plans: {created} created, {len(PLANS) - created} already existed")


if __name__ == "__main__":
    asyncio.run(seed_subscription_plans())
