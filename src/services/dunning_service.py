"""
Dunning Service

Handles dunning (payment reminder) email sequence for failed payments.
Sends escalating reminders to users with failed payments during grace period.

Dunning Schedule:
- Day 1 (1 day after failure): First reminder - informative
- Day 3 (3 days after failure): Second reminder - urgent
- Day 6 (6 days after failure): Final warning - 1 day before suspension

Each email becomes progressively more urgent to encourage payment.
"""

from datetime import datetime, timedelta, timezone
from typing import Dict, List

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.models.subscription_models.plans import SubscriptionPlan
from src.api.models.subscription_models.subscriptions import SubscriptionStatus, UserSubscription
from src.api.models.user_models.users import Users
from src.utils.logger import logger


class DunningService:
    """Service for handling payment dunning (reminder emails)."""

    def __init__(self, db: AsyncSession):
        """
        Initialize dunning service.

        Args:
            db: Database session
        """
        self.db = db

    async def get_subscriptions_for_dunning(
        self, days_since_failure: int
    ) -> List[UserSubscription]:
        """
        Get subscriptions that need dunning email for specific day.

        Finds SUSPENDED subscriptions where payment failed exactly N days ago.

        Args:
            days_since_failure: Days since payment_failed_at (1, 3, or 6)

        Returns:
            List of subscriptions needing reminder
        """
        # Calculate the target date (N days ago)
        now = datetime.now(timezone.utc)
        target_date_start = now - timedelta(days=days_since_failure, hours=1)
        target_date_end = now - timedelta(days=days_since_failure) + timedelta(hours=1)

        # Query for SUSPENDED subscriptions with payment failure in target window
        stmt = select(UserSubscription).where(
            and_(
                UserSubscription.status == SubscriptionStatus.SUSPENDED,
                UserSubscription.payment_failed_at.isnot(None),
                UserSubscription.payment_failed_at >= target_date_start,
                UserSubscription.payment_failed_at < target_date_end,
                UserSubscription.grace_period_end > now,  # Still in grace period
            )
        )

        result = await self.db.execute(stmt)
        subscriptions = result.scalars().all()

        logger.info(
            f"Found {len(subscriptions)} subscriptions for {days_since_failure}-day dunning reminder",
            extra={"days_since_failure": days_since_failure, "count": len(subscriptions)},
        )

        return subscriptions

    async def send_dunning_email_1_day(self, subscription: UserSubscription) -> bool:
        """
        Send first dunning reminder (1 day after failure).

        Tone: Helpful and informative.

        Args:
            subscription: Subscription with failed payment

        Returns:
            True if email sent successfully
        """
        try:
            from src.services.billing_email_service import BillingEmailService

            # Get user
            stmt = select(Users).where(Users.id == subscription.user_id)
            result = await self.db.execute(stmt)
            user = result.scalar_one_or_none()

            if not user:
                logger.warning(f"User not found for subscription {subscription.id}")
                return False

            # Get plan
            stmt = select(SubscriptionPlan).where(SubscriptionPlan.id == subscription.plan_id)
            result = await self.db.execute(stmt)
            plan = result.scalar_one_or_none()

            if not plan:
                logger.warning(f"Plan not found for subscription {subscription.id}")
                return False

            # Prepare email data
            plan_name = plan.name

            # Calculate amount (from plan)
            if subscription.billing_period.value == "monthly":
                amount_cents = plan.price_monthly
            else:
                amount_cents = plan.price_yearly
            amount = f"${amount_cents / 100:.2f}" if amount_cents else "N/A"

            # Send email via billing service
            email_service = BillingEmailService(self.db)
            success = await email_service.send_payment_dunning_email(
                user_id=subscription.user_id,
                plan_name=plan_name,
                amount=amount,
                days_overdue=1,
                customer_portal_url=None,  # Can be retrieved from settings if needed
            )

            if success:
                logger.info(
                    f"Sent 1-day dunning email to {user.email}",
                    extra={
                        "user_id": str(user.id),
                        "subscription_id": str(subscription.id),
                        "days_since_failure": 1,
                    },
                )

            return success

        except Exception as e:
            logger.error(
                f"Failed to send 1-day dunning email: {str(e)}",
                extra={"subscription_id": str(subscription.id), "error": str(e)},
                exc_info=True,
            )
            return False

    async def send_dunning_email_3_days(self, subscription: UserSubscription) -> bool:
        """
        Send second dunning reminder (3 days after failure).

        Tone: More urgent, emphasizing time remaining.

        Args:
            subscription: Subscription with failed payment

        Returns:
            True if email sent successfully
        """
        try:
            from src.services.billing_email_service import BillingEmailService

            # Get user and plan
            stmt = select(Users).where(Users.id == subscription.user_id)
            result = await self.db.execute(stmt)
            user = result.scalar_one_or_none()

            if not user:
                return False

            stmt = select(SubscriptionPlan).where(SubscriptionPlan.id == subscription.plan_id)
            result = await self.db.execute(stmt)
            plan = result.scalar_one_or_none()

            if not plan:
                return False

            # Calculate days until suspension
            if subscription.grace_period_end:
                grace_end = subscription.grace_period_end
                if grace_end.tzinfo is None:
                    grace_end = grace_end.replace(tzinfo=timezone.utc)
                days_until_suspension = (grace_end - datetime.now(timezone.utc)).days
            else:
                days_until_suspension = 4  # Default

            # Calculate amount
            if subscription.billing_period.value == "monthly":
                amount_cents = plan.price_monthly
            else:
                amount_cents = plan.price_yearly
            amount = f"${amount_cents / 100:.2f}" if amount_cents else "N/A"

            # Send email
            email_service = BillingEmailService(self.db)
            success = await email_service.send_payment_dunning_email(
                user_id=subscription.user_id,
                plan_name=plan.name,
                amount=amount,
                days_overdue=3,
                customer_portal_url=None,
            )

            if success:
                logger.info(
                    f"Sent 3-day dunning email to {user.email}",
                    extra={
                        "user_id": str(user.id),
                        "subscription_id": str(subscription.id),
                        "days_since_failure": 3,
                        "days_until_suspension": days_until_suspension,
                    },
                )

            return success

        except Exception as e:
            logger.error(
                f"Failed to send 3-day dunning email: {str(e)}",
                extra={"subscription_id": str(subscription.id), "error": str(e)},
                exc_info=True,
            )
            return False

    async def send_dunning_email_6_days(self, subscription: UserSubscription) -> bool:
        """
        Send final dunning warning (6 days after failure - 1 day before suspension).

        Tone: Very urgent, final notice.

        Args:
            subscription: Subscription with failed payment

        Returns:
            True if email sent successfully
        """
        try:
            from src.services.billing_email_service import BillingEmailService

            # Get user and plan
            stmt = select(Users).where(Users.id == subscription.user_id)
            result = await self.db.execute(stmt)
            user = result.scalar_one_or_none()

            if not user:
                return False

            stmt = select(SubscriptionPlan).where(SubscriptionPlan.id == subscription.plan_id)
            result = await self.db.execute(stmt)
            plan = result.scalar_one_or_none()

            if not plan:
                return False

            # Calculate amount
            if subscription.billing_period.value == "monthly":
                amount_cents = plan.price_monthly
            else:
                amount_cents = plan.price_yearly
            amount = f"${amount_cents / 100:.2f}" if amount_cents else "N/A"

            # Send email
            email_service = BillingEmailService(self.db)
            success = await email_service.send_payment_dunning_email(
                user_id=subscription.user_id,
                plan_name=plan.name,
                amount=amount,
                days_overdue=6,
                customer_portal_url=None,
            )

            if success:
                logger.info(
                    f"Sent 6-day final dunning email to {user.email}",
                    extra={
                        "user_id": str(user.id),
                        "subscription_id": str(subscription.id),
                        "days_since_failure": 6,
                    },
                )

            return success

        except Exception as e:
            logger.error(
                f"Failed to send 6-day dunning email: {str(e)}",
                extra={"subscription_id": str(subscription.id), "error": str(e)},
                exc_info=True,
            )
            return False

    async def process_dunning_reminders(self, days_since_failure: int) -> Dict[str, int]:
        """
        Process dunning reminders for specific day.

        Args:
            days_since_failure: Which day to process (1, 3, or 6)

        Returns:
            Dict with processing stats
        """
        logger.info(f"Processing {days_since_failure}-day dunning reminders...")

        # Get subscriptions needing reminder
        subscriptions = await self.get_subscriptions_for_dunning(days_since_failure)

        sent_count = 0
        failed_count = 0

        # Send appropriate email based on day
        for subscription in subscriptions:
            try:
                if days_since_failure == 1:
                    success = await self.send_dunning_email_1_day(subscription)
                elif days_since_failure == 3:
                    success = await self.send_dunning_email_3_days(subscription)
                elif days_since_failure == 6:
                    success = await self.send_dunning_email_6_days(subscription)
                else:
                    logger.warning(f"Invalid days_since_failure: {days_since_failure}")
                    continue

                if success:
                    sent_count += 1
                else:
                    failed_count += 1

            except Exception as e:
                logger.error(
                    f"Error processing dunning for subscription {subscription.id}: {str(e)}",
                    extra={"subscription_id": str(subscription.id), "error": str(e)},
                )
                failed_count += 1

        logger.info(
            f"Completed {days_since_failure}-day dunning: {sent_count} sent, {failed_count} failed",
            extra={
                "days_since_failure": days_since_failure,
                "sent": sent_count,
                "failed": failed_count,
                "total": len(subscriptions),
            },
        )

        return {
            "days_since_failure": days_since_failure,
            "total_subscriptions": len(subscriptions),
            "sent": sent_count,
            "failed": failed_count,
        }
