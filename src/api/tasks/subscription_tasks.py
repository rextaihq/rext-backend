"""
Subscription Background Tasks

Handles automated subscription management tasks:
- Trial expiry checking and notifications
- Subscription renewals
- Usage reset
- Billing reminders

These tasks should be run by a scheduler (e.g., cron, APScheduler, Celery).
"""

<<<<<<< HEAD
from datetime import datetime, timedelta, timezone
=======
from datetime import datetime, timezone, timedelta
>>>>>>> origin/dev
from typing import Dict, List
from unittest import result
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from sqlalchemy.orm import selectinload

from scripts import db
from src.api.database.async_database import get_async_db_context
from src.api.models.subscription_models.subscriptions import (
    UserSubscription,
    SubscriptionStatus
)
from src.api.models.subscription_models.plans import SubscriptionPlan
from src.api.models.user_models.users import Users
from src.services.billing_email_service import BillingEmailService
from src.utils.logger import logger
from src.utils.response_utils import success


async def check_and_notify_expiring_trials():
    """
    Check for trials expiring in 3 days and send notification emails.

    Should be run daily.

    Returns:
        Dict with notification counts
    """
    async with get_async_db_context() as db:
        try:
            # Get trials expiring in exactly 3 days
            three_days_from_now = datetime.now(timezone.utc) + timedelta(days=3)
            start_of_day = three_days_from_now.replace(hour=0, minute=0, second=0, microsecond=0)
            end_of_day = three_days_from_now.replace(hour=23, minute=59, second=59, microsecond=999999)

            # Find trials expiring in 3 days
            query = select(UserSubscription).options(
<<<<<<< HEAD
                selectinload(UserSubscription.user),
                selectinload(UserSubscription.plan)
                ).where(
            and_(
                UserSubscription.status == SubscriptionStatus.TRIAL,
                UserSubscription.trial_end_date >= start_of_day,
                UserSubscription.trial_end_date <= end_of_day
=======
                selectinload(UserSubscription.user).selectinload(Users.notification_preferences),
                selectinload(UserSubscription.plan)
            ).where(
                and_(
                    UserSubscription.status == SubscriptionStatus.TRIAL,
                    UserSubscription.trial_end_date >= start_of_day,
                    UserSubscription.trial_end_date <= end_of_day
>>>>>>> origin/dev
                )
            )      

            result = await db.execute(query)
            expiring_trials = result.scalars().all()
            logger.info(f"Found {len(expiring_trials)} trial(s) expiring in 3 days")

            # Send notifications
            email_service = BillingEmailService(db)
            success_count = 0

            for subscription in expiring_trials:
                try:
<<<<<<< HEAD
=======
                    # User and plan already eagerly loaded
>>>>>>> origin/dev
                    user = subscription.user
                    plan = subscription.plan

                    if not user or not plan:
                        continue

                    # Send trial ending email
                    success = await email_service.send_trial_ending_email(
<<<<<<< HEAD
                    user_id=user.id,
                    plan_name=plan.display_name,
                    days_remaining=3,
                    trial_end_date=subscription.trial_end_date.strftime("%B %d, %Y")
          )
=======
                        user_id=user.id,
                        plan_name=plan.display_name,
                        days_remaining=3,
                        trial_end_date=subscription.trial_end_date.strftime("%B %d, %Y"),
                        user=user,
                        preferences=user.notification_preferences
                    )
>>>>>>> origin/dev

                    if success:
                        success_count += 1
                        logger.info(f"Sent trial ending email to {user.email}")
                    else:
                        logger.warning(f"Failed to send trial ending email to {user.email}")

                except Exception as e:
                    logger.error(f"Error sending trial notification for subscription {subscription.id}: {e}")
                    continue

            logger.info(f"Successfully sent {success_count}/{len(expiring_trials)} trial ending emails")

            return {
                "total_expiring": len(expiring_trials),
                "emails_sent": success_count,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

        except Exception as e:
            logger.error(f"Error in check_and_notify_expiring_trials: {e}")
            raise


async def expire_ended_trials():
    """
    Find trials that have ended and convert them to free plan or expired status.

    Should be run daily.

    Returns:
        Dict with conversion counts
    """
    async with get_async_db_context() as db:
        try:
            now = datetime.now(timezone.utc)

            # Find trials that have ended
            query = select(UserSubscription).options(
                selectinload(UserSubscription.user).selectinload(Users.notification_preferences),
                selectinload(UserSubscription.plan)
            ).where(
                and_(
                    UserSubscription.status == SubscriptionStatus.TRIAL,
                    UserSubscription.trial_end_date < now
                )
            )

            result = await db.execute(query)
            expired_trials = result.scalars().all()

            logger.info(f"Found {len(expired_trials)} expired trial(s)")

            expired_count = 0

            for subscription in expired_trials:
                try:
                    # Mark as expired
                    subscription.status = SubscriptionStatus.EXPIRED
                    subscription.end_date = subscription.trial_end_date

                    # User and plan already eagerly loaded
                    user = subscription.user
                    plan = subscription.plan

                    if user and plan:
                        # Send trial expired email
                        email_service = BillingEmailService(db)
                        await email_service.send_trial_expired_email(
                            user_id=user.id,
                            plan_name=plan.display_name,
                            user=user,
                            preferences=user.notification_preferences
                        )

                    expired_count += 1
                    logger.info(f"Expired trial subscription {subscription.id}")

                except Exception as e:
                    logger.error(f"Error expiring trial {subscription.id}: {e}")
                    continue

            await db.commit()

            logger.info(f"Expired {expired_count} trial subscription(s)")

            return {
                "trials_expired": expired_count,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }

        except Exception as e:
            logger.error(f"Error in expire_ended_trials: {e}")
            await db.rollback()
            raise


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


# Convenience function to run all daily tasks
async def run_daily_subscription_tasks():
    """
    Run all daily subscription maintenance tasks.

    Call this from your scheduler (cron, APScheduler, etc.).
    """
    logger.info("Starting daily subscription tasks")

    results = {
        "trial_notifications": await check_and_notify_expiring_trials(),
        "trial_expirations": await expire_ended_trials(),
        "usage_resets": await reset_monthly_usage(),
    }

    logger.info(f"Daily subscription tasks completed: {results}")

    return results
