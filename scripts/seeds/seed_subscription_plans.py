"""Seed default subscription plans and user credits."""

import asyncio
from datetime import timedelta
from decimal import Decimal
from sqlalchemy import text
from uuid import uuid4

from scripts.seeds.base import get_seed_session, utc_now

PLANS = [
    {
        "name": "trial",
        "display_name": "Trial Plan",
        "description": "14-day free trial. Test the full pipeline before committing.",
        "price_monthly": Decimal("0.00"),
        "price_yearly": Decimal("0.00"),
        "credits_per_month": 50,
        "is_trial_plan": True,
        "features": {
            "trial_duration_days": 14,
            "collaboration": "Basic",
            "support": "Community",
            "api_access": "Limited",
        },
        "max_workspaces": 1,
        "max_members_per_workspace": 3,
        "max_topics": 10,
        "max_knowledge_items": 20,
        "max_api_calls_per_month": 100,
        "is_active": True,
        "is_public": False,
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
            "collaboration": "Basic",
            "support": "Email",
            "api_access": "Limited",
        },
        "max_workspaces": 1,
        "max_members_per_workspace": 5,
        "max_topics": 100,
        "max_knowledge_items": 500,
        "max_api_calls_per_month": 5000,
        "is_active": True,
        "is_public": True,
    },
    {
        "name": "growth",
        "display_name": "Growth",
        "description": "For small teams — most popular plan.",
        "price_monthly": Decimal("89.00"),
        "price_yearly": Decimal("890.00"),
        "credits_per_month": 1000,
        "is_trial_plan": False,
        "features": {
            "collaboration": "Advanced",
            "support": "Email & Chat",
            "api_access": "Standard",
        },
        "max_workspaces": 3,
        "max_members_per_workspace": 10,
        "max_topics": 300,
        "max_knowledge_items": 2000,
        "max_api_calls_per_month": 20000,
        "is_active": True,
        "is_public": True,
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
            "collaboration": "Advanced",
            "support": "Priority Email & Chat",
            "api_access": "Full",
        },
        "max_workspaces": 5,
        "max_members_per_workspace": 15,
        "max_topics": 500,
        "max_knowledge_items": 5000,
        "max_api_calls_per_month": 50000,
        "is_active": True,
        "is_public": True,
    },
    {
        "name": "agency",
        "display_name": "Agency",
        "description": "For agencies and white-label resellers.",
        "price_monthly": Decimal("399.00"),
        "price_yearly": Decimal("3990.00"),
        "credits_per_month": 5500,
        "is_trial_plan": False,
        "features": {
            "collaboration": "Enterprise",
            "support": "Dedicated Support",
            "api_access": "Full",
        },
        "max_workspaces": -1,
        "max_members_per_workspace": -1,
        "max_topics": -1,
        "max_knowledge_items": -1,
        "max_api_calls_per_month": -1,
        "is_active": True,
        "is_public": True,
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
            "collaboration": "Enterprise",
            "support": "24/7 Priority",
            "api_access": "Unlimited",
            "dedicated_account_manager": True,
            "custom_integrations": True,
            "sla_guarantee": True,
        },
        "max_workspaces": -1,
        "max_members_per_workspace": -1,
        "max_topics": -1,
        "max_knowledge_items": -1,
        "max_api_calls_per_month": -1,
        "is_active": True,
        "is_public": False,
    },
]


async def seed_subscription_plans():
    """Seed & update default subscription plans and user credits (idempotent)."""
    async with get_seed_session() as session:
        created = 0
        updated = 0

        for plan in PLANS:
            result = await session.execute(
                text("SELECT id FROM subscription_plans WHERE name = :name"), {"name": plan["name"]}
            )
            row = result.fetchone()
            if row:
                await session.execute(
                    text("""
                        UPDATE subscription_plans SET
                            display_name = :display_name,
                            description = :description,
                            price_monthly = :price_monthly,
                            price_yearly = :price_yearly,
                            credits_per_month = :credits_per_month,
                            is_trial_plan = :is_trial_plan,
                            features = :features,
                            max_workspaces = :max_workspaces,
                            max_members_per_workspace = :max_members_per_workspace,
                            max_topics = :max_topics,
                            max_knowledge_items = :max_knowledge_items,
                            max_api_calls_per_month = :max_api_calls_per_month,
                            is_active = :is_active,
                            is_public = :is_public,
                            updated_at = :updated_at
                        WHERE name = :name
                    """),
                    {
                        "name": plan["name"],
                        "display_name": plan["display_name"],
                        "description": plan["description"],
                        "price_monthly": plan["price_monthly"],
                        "price_yearly": plan["price_yearly"],
                        "credits_per_month": plan["credits_per_month"],
                        "is_trial_plan": plan["is_trial_plan"],
                        "features": plan["features"],
                        "max_workspaces": plan["max_workspaces"],
                        "max_members_per_workspace": plan["max_members_per_workspace"],
                        "max_topics": plan["max_topics"],
                        "max_knowledge_items": plan["max_knowledge_items"],
                        "max_api_calls_per_month": plan["max_api_calls_per_month"],
                        "is_active": plan["is_active"],
                        "is_public": plan["is_public"],
                        "updated_at": utc_now(),
                    },
                )
                updated += 1
            else:
                await session.execute(
                    text("""
                        INSERT INTO subscription_plans (
                            id, name, display_name, description, price_monthly, price_yearly, 
                            credits_per_month, is_trial_plan, features, max_workspaces, 
                            max_members_per_workspace, max_topics, max_knowledge_items, 
                            max_api_calls_per_month, is_active, is_public, created_at, updated_at
                        ) VALUES (
                            :id, :name, :display_name, :description, :price_monthly, :price_yearly, 
                            :credits_per_month, :is_trial_plan, :features, :max_workspaces, 
                            :max_members_per_workspace, :max_topics, :max_knowledge_items, 
                            :max_api_calls_per_month, :is_active, :is_public, :created_at, :updated_at
                        )
                    """),
                    {
                        "id": uuid4(),
                        "name": plan["name"],
                        "display_name": plan["display_name"],
                        "description": plan["description"],
                        "price_monthly": plan["price_monthly"],
                        "price_yearly": plan["price_yearly"],
                        "credits_per_month": plan["credits_per_month"],
                        "is_trial_plan": plan["is_trial_plan"],
                        "features": plan["features"],
                        "max_workspaces": plan["max_workspaces"],
                        "max_members_per_workspace": plan["max_members_per_workspace"],
                        "max_topics": plan["max_topics"],
                        "max_knowledge_items": plan["max_knowledge_items"],
                        "max_api_calls_per_month": plan["max_api_calls_per_month"],
                        "is_active": plan["is_active"],
                        "is_public": plan["is_public"],
                        "created_at": utc_now(),
                        "updated_at": utc_now(),
                    },
                )
                created += 1

        print(f"Subscription plans: {created} created, {updated} updated")

        # Seed credits for existing users
        await seed_user_credits(session)


async def seed_user_credits(session):
    """Assign active user_subscriptions with credits for users in the database."""
    res = await session.execute(text("SELECT id, credits_per_month FROM subscription_plans WHERE name = 'growth'"))
    growth_plan = res.fetchone()
    if not growth_plan:
        res = await session.execute(text("SELECT id, credits_per_month FROM subscription_plans WHERE name = 'pro'"))
        growth_plan = res.fetchone()

    if not growth_plan:
        print("⚠️ No growth or pro plan found to seed user credits.")
        return

    plan_id, credits = growth_plan.id, growth_plan.credits_per_month or 1000

    users_res = await session.execute(text("SELECT id, email FROM users"))
    users = users_res.fetchall()

    subs_created = 0
    subs_updated = 0

    now = utc_now()
    reset_date = now + timedelta(days=30)

    for user in users:
        user_id = user.id
        sub_res = await session.execute(
            text("SELECT id, current_credits FROM user_subscriptions WHERE user_id = :user_id AND status IN ('active', 'trial')"),
            {"user_id": user_id},
        )
        existing_sub = sub_res.fetchone()

        if existing_sub:
            if (existing_sub.current_credits or 0) <= 0:
                await session.execute(
                    text("""
                        UPDATE user_subscriptions SET
                            current_credits = :credits,
                            credits_reset_date = :reset_date,
                            updated_at = :now
                        WHERE id = :sub_id
                    """),
                    {
                        "credits": credits,
                        "reset_date": reset_date,
                        "now": now,
                        "sub_id": existing_sub.id,
                    },
                )
                subs_updated += 1
        else:
            await session.execute(
                text("""
                    INSERT INTO user_subscriptions (
                        id, user_id, plan_id, status, billing_period, start_date,
                        current_credits, credits_reset_date, created_at, updated_at
                    ) VALUES (
                        :id, :user_id, :plan_id, 'active', 'monthly', :now,
                        :credits, :reset_date, :now, :now
                    )
                """),
                {
                    "id": uuid4(),
                    "user_id": user_id,
                    "plan_id": plan_id,
                    "now": now,
                    "credits": credits,
                    "reset_date": reset_date,
                },
            )
            subs_created += 1

    print(f"User credits: {subs_created} subscriptions created, {subs_updated} updated with {credits} credits")


if __name__ == "__main__":
    asyncio.run(seed_subscription_plans())

