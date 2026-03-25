import asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from src.api.database.async_database import AsyncSessionLocal
from src.api.models.subscription_models.subscriptions import UserSubscription
from src.api.models.subscription_models.plans import SubscriptionPlan

# Fetch a real subscription for a given user
async def get_my_subscription_async(user_id: str, db: AsyncSession):
    """
    Fetch the active subscription for a user.
    """
    stmt = (
        select(UserSubscription)
        .where(UserSubscription.user_id == user_id)
        .order_by(UserSubscription.created_at.desc())  # latest subscription first
    )
    result = await db.execute(stmt)
    subscription = result.scalar_one_or_none()  # get first row or None
    if subscription:
        plan_stmt = select(SubscriptionPlan).where(SubscriptionPlan.id == subscription.plan_id)
        plan_result = await db.execute(plan_stmt)
        plan = plan_result.scalar_one_or_none()
        return {
            "user_id": user_id,
            "subscription_id": str(subscription.id),
            "plan_name": plan.name if plan else None,
            "status": subscription.status,
            "start_date": subscription.start_date.isoformat() if subscription.start_date else None,
            "end_date": subscription.end_date.isoformat() if subscription.end_date else None,
        }
    return {"user_id": user_id, "subscription": None}

# Test runner
async def main():
    async with AsyncSessionLocal() as db:
        user_id = "9f7d7ae2-5a96-44de-9097-65bbfd66a7bb"  # replace with your real user_id
        subscription = await get_my_subscription_async(user_id, db)
        print("Subscription result:", subscription)

if __name__ == "__main__":
    asyncio.run(main())