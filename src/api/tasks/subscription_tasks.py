"""
Subscription Background Tasks

Handles automated subscription management tasks:
- Usage reset

Note: Trial expiration and notifications are handled by
src/api/tasks/trial_expiration_task.py (runs at midnight).
Do NOT add trial logic here to avoid duplication.
"""

from datetime import datetime, timedelta, timezone
from typing import Dict
from sqlalchemy import select, and_

from src.api.database.async_database import get_async_db_context
from src.api.models.subscription_models.subscriptions import (
    UserSubscription,
    SubscriptionStatus
)
from src.utils.logger import logger


async def reset_monthly_usage():
    """
    Reset API call usage for all active subscriptions on their monthly reset date.

    Should be run daily.

    Returns:
        Dict with reset counts
    """
    async with get_async_db_context() as db:
        try:
            now = datetime.now(timezone.utc)
            today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            today_end = now.replace(hour=23, minute=59, second=59, microsecond=999999)

            # Find subscriptions with usage reset date = today.
            # Subscriptions pending cancellation are excluded — they're due to be
            # finalized (not renewed) by finalize_expired_cancellations.
            query = select(UserSubscription).where(
                and_(
                    UserSubscription.status.in_([SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL]),
                    UserSubscription.cancel_at_period_end.is_(False),
                    UserSubscription.usage_reset_date >= today_start,
                    UserSubscription.usage_reset_date <= today_end
                )
            )

            result = await db.execute(query)
            subscriptions_to_reset = result.scalars().all()

            logger.info(f"Found {len(subscriptions_to_reset)} subscription(s) to reset usage")

            reset_count = 0

            for subscription in subscriptions_to_reset:
                try:
                    # Reset API call counter
                    subscription.current_api_calls = 0
                    subscription.usage_reset_date = now + timedelta(days=30)

                    reset_count += 1

                except Exception as e:
                    logger.error(f"Error resetting usage for subscription {subscription.id}: {e}")
                    continue

            await db.commit()

            logger.info(f"Reset usage for {reset_count} subscription(s)")

            return {
                "subscriptions_reset": reset_count,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

        except Exception as e:
            logger.error(f"Error in reset_monthly_usage: {e}")
            await db.rollback()
            raise


async def finalize_expired_cancellations() -> Dict:
    """
    Finalize subscriptions whose deferred cancellation grace period has ended.

    Deferred cancellations (cancel_at_period_end=True) keep their status and
    credits until end_date so the user retains access for the period they
    already paid for. Once end_date passes, this task cuts them over:
    status -> CANCELLED and credits zeroed.

    Should be run daily, before reset_monthly_usage.

    Returns:
        Dict with finalized counts
    """
    async with get_async_db_context() as db:
        try:
            now = datetime.now(timezone.utc)

            query = select(UserSubscription).where(
                and_(
                    UserSubscription.cancel_at_period_end.is_(True),
                    UserSubscription.status.in_([SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL]),
                    UserSubscription.end_date.is_not(None),
                    UserSubscription.end_date <= now
                )
            )

            result = await db.execute(query)
            subscriptions_to_finalize = result.scalars().all()

            logger.info(f"Found {len(subscriptions_to_finalize)} pending cancellation(s) to finalize")

            finalized_count = 0

            for subscription in subscriptions_to_finalize:
                try:
                    subscription.status = SubscriptionStatus.CANCELLED
                    subscription.current_credits = 0
                    subscription.updated_at = now
                    finalized_count += 1
                except Exception as e:
                    logger.error(f"Error finalizing cancellation for subscription {subscription.id}: {e}")
                    continue

            await db.commit()

            logger.info(f"Finalized {finalized_count} pending cancellation(s)")

            return {
                "subscriptions_finalized": finalized_count,
                "timestamp": now.isoformat()
            }

        except Exception as e:
            logger.error(f"Error in finalize_expired_cancellations: {e}")
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
        # Must run before usage_resets so a subscription whose grace period
        # ends today is cancelled rather than renewed for another cycle.
        "cancellations_finalized": await finalize_expired_cancellations(),
        "usage_resets": await reset_monthly_usage(),
    }

    logger.info(f"Daily subscription maintenance completed: {results}")

    return results
