"""Give a promotion's bonus to paid subscriptions started in its window before the grant existed.

The webhook grants a promotion's bonus when a subscription is created. A
subscription created inside a promotion's window before that code was deployed
got none. This finds them (paid and still with access, a cancellation paid
through to its end included, a trial not yet paid excluded; started inside a
promotion's window; no grant yet; its paying order known, so a refunded one is
skipped) and, with --apply, grants through the same path as the webhook:
once per subscription, never for a refunded order. Without --apply it only
lists them. It prints subscription ids and counts, no personal data.

    python scripts/backfill_promotion_bonuses.py            # list what would be granted
    python scripts/backfill_promotion_bonuses.py --apply    # grant
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from datetime import timedelta  # noqa: E402

from sqlalchemy import exists, func, or_, select  # noqa: E402
from sqlalchemy.orm import selectinload  # noqa: E402

from src.api.database.async_database import get_async_db_context  # noqa: E402
from src.api.models.subscription_models.credit_grants import CreditGrant  # noqa: E402
from src.api.models.subscription_models.orders import Order  # noqa: E402
from src.api.models.subscription_models.promotions import Promotion  # noqa: E402
from src.api.models.subscription_models.subscriptions import (  # noqa: E402
    SubscriptionStatus,
    UserSubscription,
    subscription_grants_access,
)
from src.services.credit_grants import as_utc, grant_promotion_bonus  # noqa: E402


async def main(apply: bool) -> None:
    async with get_async_db_context() as db:
        promotions = (
            (await db.execute(select(Promotion).where(Promotion.is_active.is_(True))))
            .scalars()
            .all()
        )
        if not promotions:
            print("No active promotion.")
            return
        earliest = min(as_utc(p.starts_at) for p in promotions)
        latest = max(as_utc(p.ends_at) for p in promotions)
        candidates = (
            (
                await db.execute(
                    select(UserSubscription)
                    .options(selectinload(UserSubscription.plan))
                    .where(
                        # Paid and still with access: a cancellation paid through
                        # to its end date qualifies, a trial not yet paid does not.
                        subscription_grants_access(),
                        UserSubscription.status != SubscriptionStatus.TRIAL,
                        UserSubscription.start_date >= earliest,
                        UserSubscription.start_date < latest,
                        ~exists().where(CreditGrant.subscription_id == UserSubscription.id),
                    )
                    .order_by(UserSubscription.start_date)
                )
            )
            .scalars()
            .all()
        )

        async def earning_order(subscription):
            """The Lemon Squeezy order that paid for the subscription, if it can be told."""
            if subscription.lemonsqueezy_order_id:
                return subscription.lemonsqueezy_order_id
            start = as_utc(subscription.start_date)
            return await db.scalar(
                select(Order.lemonsqueezy_order_id)
                .where(
                    Order.user_id == subscription.user_id,
                    or_(
                        Order.subscription_id == subscription.id,
                        func.coalesce(Order.ordered_at, Order.created_at).between(
                            start - timedelta(days=1), start + timedelta(days=1)
                        ),
                    ),
                )
                .order_by(func.coalesce(Order.ordered_at, Order.created_at))
                .limit(1)
            )

        granted = 0
        for subscription in candidates:
            if not subscription.plan or subscription.plan.is_trial_plan:
                continue
            period = subscription.billing_period.value if subscription.billing_period else None
            order_id = await earning_order(subscription)
            if not order_id:
                # Without its order a refund cannot be ruled out: grant by hand if right.
                print(f"skipped (no order found): subscription {subscription.id}")
                continue
            if not apply:
                print(
                    f"would check: subscription {subscription.id} started {subscription.start_date}"
                )
                continue
            amount = await grant_promotion_bonus(
                db,
                subscription.id,
                subscription.plan,
                period,
                subscription.start_date,
                subscription.credits_reset_date,
                paid_from=subscription.start_date,
                order_id=order_id,
            )
            if amount:
                granted += 1
                print(f"granted {amount} credits: subscription {subscription.id}")
        if apply:
            await db.commit()
            print(f"Granted {granted} of {len(candidates)} candidate subscription(s).")
        else:
            print(f"{len(candidates)} candidate subscription(s); run with --apply to grant.")


if __name__ == "__main__":
    asyncio.run(main("--apply" in sys.argv))
