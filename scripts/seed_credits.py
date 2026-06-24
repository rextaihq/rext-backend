"""Seed credits to a user account by email. One-shot dev utility."""
import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

load_dotenv()
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.api.models.subscription_models.subscriptions import UserSubscription, SubscriptionStatus, BillingPeriod
from src.api.models.subscription_models.plans import SubscriptionPlan
from src.api.models.user_models.users import Users


async def seed_credits(email: str, amount: int) -> None:
    database_url = os.getenv("POSTGRES_URI_CUSTOM") or os.getenv("DATABASE_URL")
    for prefix in ("postgresql+psycopg://", "postgresql+psycopg2://", "postgresql://"):
        if database_url.startswith(prefix):
            database_url = "postgresql+asyncpg://" + database_url[len(prefix):]
            break

    engine = create_async_engine(database_url, echo=False)
    Session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with Session() as db:
        user_result = await db.execute(select(Users).where(Users.email == email))
        user = user_result.scalar_one_or_none()
        if not user:
            print(f"ERROR: user {email!r} not found")
            return

        pro_plan_result = await db.execute(
            select(SubscriptionPlan).where(SubscriptionPlan.name == "pro")
        )
        pro_plan = pro_plan_result.scalar_one_or_none()
        if not pro_plan:
            print("ERROR: 'pro' plan not found in subscription_plans table")
            return

        sub_result = await db.execute(
            select(UserSubscription).where(UserSubscription.user_id == user.id)
        )
        subscription = sub_result.scalar_one_or_none()

        if not subscription:
            subscription = UserSubscription(
                user_id=user.id,
                plan_id=pro_plan.id,
                status=SubscriptionStatus.ACTIVE,
                billing_period=BillingPeriod.MONTHLY,
                current_credits=amount,
            )
            db.add(subscription)
            print(f"OK: created pro subscription for {email} with {amount} credits")
        else:
            prev = subscription.current_credits
            subscription.plan_id = pro_plan.id
            subscription.status = SubscriptionStatus.ACTIVE
            subscription.current_credits = amount
            subscription.end_date = None
            print(f"OK: {email} → pro plan, credits {prev} → {amount}")

        await db.commit()

    await engine.dispose()


if __name__ == "__main__":
    email = sys.argv[1] if len(sys.argv) > 1 else "it@revnix.com"
    amount = int(sys.argv[2]) if len(sys.argv) > 2 else 1000
    asyncio.run(seed_credits(email, amount))
