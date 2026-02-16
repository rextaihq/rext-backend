"""
Trial expiration background task.

This task should be scheduled to run daily (recommended at midnight UTC).
It checks for expiring trials and sends reminder emails.
"""
import asyncio
from datetime import datetime, timezone
from typing import List
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.database.async_database import get_async_db_context
from src.api.models.subscription_models.subscriptions import UserSubscription
from src.services.trial_service import TrialService
from src.services.email_service import EmailService
from src.utils.logger import logger


class TrialExpirationTask:
    """Background task for trial expiration management."""

    def __init__(self, db: AsyncSession):
        """Initialize task with database session."""
        self.db = db
        self.trial_service = TrialService(db)
        self.email_service = EmailService(db)

    async def send_trial_reminder_email(
        self,
        subscription: UserSubscription,
        days_remaining: int
    ) -> bool:
        """
        Send trial reminder email to user.

        Args:
            subscription: User subscription
            days_remaining: Days remaining in trial

        Returns:
            True if email sent successfully
        """
        try:
            # Get user email
            user = subscription.user
            if not user or not user.email:
                logger.warning(
                    f"Cannot send trial reminder - user/email not found for subscription {subscription.id}"
                )
                return False

            # Prepare email context
            context = {
                "user_name": user.name or user.email,
                "plan_name": subscription.plan.name if subscription.plan else "Unknown Plan",
                "days_remaining": days_remaining,
                "trial_end_date": subscription.trial_end_date.strftime("%B %d, %Y") if subscription.trial_end_date else "Unknown",
                "upgrade_url": f"{self._get_app_url()}/pricing",
                "manage_url": f"{self._get_app_url()}/subscription"
            }

            # Select email template based on days remaining
            if days_remaining == 3:
                subject = f"Your trial ends in 3 days"
                template = "trial_reminder_3_days"
            elif days_remaining == 1:
                subject = f"Your trial ends tomorrow"
                template = "trial_reminder_1_day"
            else:  # 0 days
                subject = f"Your trial ends today"
                template = "trial_reminder_expiring_today"

            # Send email
            await self.email_service.send_email(
                to_email=user.email,
                subject=subject,
                template_name=template,
                context=context
            )

            logger.info(
                f"Trial reminder email sent to {user.email}",
                extra={
                    "user_id": str(user.id),
                    "subscription_id": str(subscription.id),
                    "days_remaining": days_remaining
                }
            )

            return True

        except Exception as e:
            logger.error(
                f"Failed to send trial reminder email: {str(e)}",
                extra={
                    "subscription_id": str(subscription.id),
                    "days_remaining": days_remaining,
                    "error": str(e)
                }
            )
            return False

    async def send_trial_expired_email(
        self,
        subscription: UserSubscription
    ) -> bool:
        """
        Send trial expired email to user.

        Args:
            subscription: Expired subscription

        Returns:
            True if email sent successfully
        """
        try:
            user = subscription.user
            if not user or not user.email:
                return False

            context = {
                "user_name": user.name or user.email,
                "plan_name": subscription.plan.name if subscription.plan else "Unknown Plan",
                "upgrade_url": f"{self._get_app_url()}/pricing",
                "support_url": f"{self._get_app_url()}/support"
            }

            await self.email_service.send_email(
                to_email=user.email,
                subject="Your trial has expired",
                template_name="trial_expired",
                context=context
            )

            logger.info(
                f"Trial expired email sent to {user.email}",
                extra={
                    "user_id": str(user.id),
                    "subscription_id": str(subscription.id)
                }
            )

            return True

        except Exception as e:
            logger.error(
                f"Failed to send trial expired email: {str(e)}",
                extra={
                    "subscription_id": str(subscription.id),
                    "error": str(e)
                }
            )
            return False

    async def process_expiring_trials(self, days_remaining: int) -> int:
        """
        Process trials expiring in N days.

        Args:
            days_remaining: Number of days until expiration

        Returns:
            Number of reminders sent
        """
        logger.info(f"Processing trials expiring in {days_remaining} days...")

        trials = await self.trial_service.get_expiring_trials(days_remaining)

        logger.info(f"Found {len(trials)} trials expiring in {days_remaining} days")

        sent_count = 0
        for subscription in trials:
            success = await self.send_trial_reminder_email(subscription, days_remaining)
            if success:
                sent_count += 1

        logger.info(f"Sent {sent_count}/{len(trials)} trial reminder emails")

        return sent_count

    async def process_expired_trials(self) -> int:
        """
        Process trials that have already expired.

        Returns:
            Number of trials expired
        """
        logger.info("Processing expired trials...")

        expired_trials = await self.trial_service.get_expired_trials()

        logger.info(f"Found {len(expired_trials)} expired trials")

        expired_count = 0
        for subscription in expired_trials:
            try:
                # Update status to expired
                await self.trial_service.expire_trial(subscription.id)

                # Send expiration email
                await self.send_trial_expired_email(subscription)

                expired_count += 1

            except Exception as e:
                logger.error(
                    f"Failed to process expired trial {subscription.id}: {str(e)}",
                    extra={
                        "subscription_id": str(subscription.id),
                        "error": str(e)
                    }
                )

        # Commit all changes
        await self.db.commit()

        logger.info(f"Expired {expired_count}/{len(expired_trials)} trials")

        return expired_count

    async def run(self):
        """
        Run the trial expiration task.

        This method should be called by a scheduler (cron, Celery, etc.).
        """
        logger.info("=== Trial Expiration Task Started ===")

        try:
            # Process trials expiring in 3 days
            await self.process_expiring_trials(days_remaining=3)

            # Process trials expiring in 1 day
            await self.process_expiring_trials(days_remaining=1)

            # Process trials expiring today
            await self.process_expiring_trials(days_remaining=0)

            # Process already expired trials
            await self.process_expired_trials()

            logger.info("=== Trial Expiration Task Completed Successfully ===")

        except Exception as e:
            logger.error(
                f"Trial expiration task failed: {str(e)}",
                extra={"error": str(e)}
            )
            raise

    def _get_app_url(self) -> str:
        """Get the application base URL from environment."""
        import os
        return os.getenv("FRONTEND_URL", "http://localhost:3000")


async def run_trial_expiration_task():
    """
    Entry point for running the trial expiration task.

    This can be called by a cron job or scheduler.
    """
    async with get_async_db_context() as db:
        task = TrialExpirationTask(db)
        await task.run()


if __name__ == "__main__":
    """
    Run this script directly for testing or manual execution:

    python -m src.api.tasks.trial_expiration_task
    """
    asyncio.run(run_trial_expiration_task())
