"""
Local dev script to manually activate a subscription after LemonSqueezy checkout.

WHY THIS EXISTS:
  LemonSqueezy sends a `subscription_created` webhook after payment, but when
  running locally the webhook endpoint is unreachable. This script directly writes
  the subscription record that the webhook would have created.

USAGE:
  .venv/bin/python3 activate_sub.py

Edit USER_ID and PLAN_NAME below as needed.
"""

import asyncio
import uuid
from datetime import datetime, timezone, timedelta

from sqlalchemy.future import select
from src.api.database.async_database import AsyncSessionLocal
from src.api.models.subscription_models.subscriptions import (
    UserSubscription,
    SubscriptionStatus,
    BillingPeriod,
)
from src.api.models.subscription_models.plans import SubscriptionPlan
from src.api.models.user_models.users import Users

# ── Config ───────────────────────────────────────────────────────────────────
USER_ID   = "9f7d7ae2-5a96-44de-9097-65bbfd66a7bb"
PLAN_NAME = "pro"           # free | basic | pro | enterprise
BILLING   = BillingPeriod.MONTHLY
# ─────────────────────────────────────────────────────────────────────────────


async def activate():
    async with AsyncSessionLocal() as db:
        # 1. Fetch user
        user_result = await db.execute(select(Users).where(Users.id == USER_ID))
        user = user_result.scalar_one_or_none()
        if not user:
            print(f"[ERROR] User {USER_ID} not found")
            return

        # 2. Fetch plan
        plan_result = await db.execute(
            select(SubscriptionPlan).where(SubscriptionPlan.name == PLAN_NAME)
        )
        plan = plan_result.scalar_one_or_none()
        if not plan:
            print(f"[ERROR] Plan '{PLAN_NAME}' not found")
            return

        # 3. Cancel any existing active subscription for this user
        existing_result = await db.execute(
            select(UserSubscription)
            .where(UserSubscription.user_id == USER_ID)
            .where(UserSubscription.status == SubscriptionStatus.ACTIVE)
        )
        existing = existing_result.scalar_one_or_none()
        if existing:
            print(f"[INFO] Cancelling existing active subscription {existing.id}")
            existing.status = SubscriptionStatus.CANCELLED
            existing.end_date = datetime.now(timezone.utc)

        # 4. Create new active subscription
        now = datetime.now(timezone.utc)
        sub = UserSubscription(
            id=uuid.uuid4(),
            user_id=USER_ID,
            plan_id=plan.id,
            status=SubscriptionStatus.ACTIVE,
            billing_period=BILLING,
            start_date=now,
            end_date=None,
            renews_at=now + timedelta(days=30),
            provider_subscription_id=f"dev_sub_{uuid.uuid4().hex[:12]}",
            provider_customer_id=f"dev_cust_{uuid.uuid4().hex[:12]}",
            lemonsqueezy_subscription_id=f"dev_ls_{uuid.uuid4().hex[:12]}",
            lemonsqueezy_customer_id=f"dev_lscust_{uuid.uuid4().hex[:10]}",
            current_api_calls=0,
        )
        db.add(sub)

        # 5. Update user's provider_customer_id (remove temp_ prefix so the
        #    pending-state guard in get_my_subscription works correctly)
        user.provider_customer_id = sub.provider_customer_id

        await db.commit()
        print(f"[OK] Subscription activated!")
        print(f"     user_id   : {USER_ID}")
        print(f"     plan      : {plan.name} ({plan.display_name})")
        print(f"     sub_id    : {sub.id}")
        print(f"     status    : {sub.status.value}")
        print(f"     renews_at : {sub.renews_at.date()}")


if __name__ == "__main__":
    asyncio.run(activate())
