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
from src.api.models import *
from src.api.models.subscription_models import *
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

            # Find subscriptions with usage reset date = today
            query = select(UserSubscription).where(
                and_(
                    UserSubscription.status.in_([SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL]),
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
