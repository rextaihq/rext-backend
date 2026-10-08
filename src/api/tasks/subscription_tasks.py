"""
Subscription Background Tasks

Handles automated subscription management tasks:
- Usage reset

Note: Trial expiration and notifications are handled by
src/api/tasks/trial_expiration_task.py (runs at midnight).
Do NOT add trial logic here to avoid duplication.
"""

from datetime import datetime, timezone

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import selectinload

from src.api.database.async_database import get_async_db_context
from src.api.models.subscription_models.subscriptions import SubscriptionStatus, UserSubscription
from src.utils.datetime_utils import next_billing_anchor
from src.utils.logger import logger


async def reset_monthly_usage():
    """
    Reset API call usage and monthly credits for subscriptions whose billing
    period has rolled over.

    Should be run daily. The next reset date is advanced with ``next_billing_anchor``
    so the billing day stays anchored to the original period boundary (calendar
    month cadence) instead of drifting by a fixed 30 days. A subscription that
    missed several daily runs is caught up through every elapsed period in one
    pass.

    Returns:
        Dict with reset counts
    """
    async with get_async_db_context() as db:
        try:
            now = datetime.now(timezone.utc)
            today_end = now.replace(hour=23, minute=59, second=59, microsecond=999999)

            # Find subscriptions whose usage and/or credits reset date is now due
            # (today or earlier - earlier picks up any days the job missed).
            query = (
                select(UserSubscription)
                .options(selectinload(UserSubscription.plan))
                .where(
                    and_(
                        UserSubscription.status.in_(
                            [SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL]
                        ),
                        or_(
                            UserSubscription.usage_reset_date <= today_end,
                            UserSubscription.credits_reset_date <= today_end,
                        ),
                    )
                )
            )

            result = await db.execute(query)
            subscriptions_to_reset = result.scalars().all()

            logger.info(
                f"Found {len(subscriptions_to_reset)} subscription(s) to reset usage/credits"
            )

            usage_reset_count = 0
            credits_reset_count = 0

            for subscription in subscriptions_to_reset:
                try:
                    if subscription.usage_reset_date and subscription.usage_reset_date <= today_end:
                        # The legacy counter still goes to zero with its anchor. Nothing here
                        # reads it any more, but the release before this one does, and it only
                        # clears a count whose date has passed: during a deploy, or after a
                        # rollback, it would hold last month's count for a whole period. It
                        # goes when the column does.
                        subscription.current_api_calls = 0
                        subscription.usage_reset_date = next_billing_anchor(
                            subscription.usage_reset_date, now
                        )
                        usage_reset_count += 1

                    plan = subscription.plan
                    if (
                        plan
                        and not plan.is_trial_plan
                        and subscription.credits_reset_date
                        and subscription.credits_reset_date <= today_end
                    ):
                        subscription.current_credits = plan.credits_per_month or 0
                        subscription.credits_reset_date = next_billing_anchor(
                            subscription.credits_reset_date, now
                        )
                        credits_reset_count += 1

                    subscription.updated_at = now

                except Exception as e:
                    logger.error(
                        f"Error resetting usage/credits for subscription {subscription.id}: {e}"
                    )
                    continue

            await db.commit()

            logger.info(
                f"Reset usage for {usage_reset_count} subscription(s), "
                f"credits for {credits_reset_count} subscription(s)"
            )

            return {
                "subscriptions_reset": usage_reset_count,
                "credits_reset": credits_reset_count,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        except Exception as e:
            logger.error(f"Error in reset_monthly_usage: {e}")
            await db.rollback()
            raise


async def run_daily_subscription_tasks():
    """
    Run daily subscription maintenance tasks (excluding trial management).

    Trial expiration and notifications are handled separately by
    TrialExpirationTask (scheduled at midnight).
    """
    logger.info("Starting daily subscription maintenance tasks")

    results = {
        "usage_resets": await reset_monthly_usage(),
    }

    logger.info(f"Daily subscription maintenance completed: {results}")

    return results
