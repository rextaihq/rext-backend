"""
Grace Period Service

Handles automatic suspension of subscriptions after grace period expires.

Grace Period Flow:
1. Payment fails → Status set to SUSPENDED with 7-day grace period
2. Dunning emails sent on days 1, 3, 6
3. Day 7 (grace period expires) → This service suspends to EXPIRED
4. User access removed, expiration email sent
"""

from typing import List, Dict
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from src.api.models.subscription_models.subscriptions import (
    UserSubscription,
    SubscriptionStatus
)
from src.api.models.subscription_models.plans import SubscriptionPlan
from src.api.models.user_models.users import Users
from src.utils.logger import logger


class GracePeriodService:
    """Service for handling grace period expiration and suspension."""

    def __init__(self, db: AsyncSession):
        """
        Initialize grace period service.

        Args:
            db: Database session
        """
        self.db = db

    async def get_expired_grace_periods(self) -> List[UserSubscription]:
        """
        Get subscriptions with expired grace periods.

        Finds SUSPENDED subscriptions where grace_period_end has passed.

        Returns:
            List of subscriptions past grace period
        """
        now = datetime.now(timezone.utc)

        # Query for SUSPENDED subscriptions with expired grace period
        stmt = select(UserSubscription).where(
            and_(
                UserSubscription.status == SubscriptionStatus.SUSPENDED,
                UserSubscription.grace_period_end.isnot(None),
                UserSubscription.grace_period_end <= now
            )
        )

        result = await self.db.execute(stmt)
        subscriptions = result.scalars().all()

        logger.info(
            f"Found {len(subscriptions)} subscriptions with expired grace periods",
            extra={"count": len(subscriptions)}
        )

        return subscriptions

    async def suspend_subscription(
        self,
        subscription: UserSubscription
    ) -> bool:
        """
        Suspend subscription after grace period expiration.

        Actions:
        1. Update status to EXPIRED
        2. Set end_date to now
        3. Clear grace period fields
        4. Send suspension email

        Args:
            subscription: Subscription to suspend

        Returns:
            True if suspension successful
        """
        try:
            # Get user for email
            stmt = select(Users).where(Users.id == subscription.user_id)
            result = await self.db.execute(stmt)
            user = result.scalar_one_or_none()

            if not user:
                logger.warning(
                    f"User not found for subscription {subscription.id}",
                    extra={"subscription_id": str(subscription.id)}
                )
                return False

            # Get plan for email
            stmt = select(SubscriptionPlan).where(SubscriptionPlan.id == subscription.plan_id)
            result = await self.db.execute(stmt)
            plan = result.scalar_one_or_none()

            # Update subscription status
            now = datetime.now(timezone.utc)
            subscription.status = SubscriptionStatus.EXPIRED
            subscription.end_date = now
            subscription.updated_at = now

            # Clear grace period tracking (no longer needed)
            # Keep payment_failed_at for analytics
            subscription.grace_period_end = None

            await self.db.flush()

            logger.info(
                f"Suspended subscription {subscription.id} after grace period expiration",
                extra={
                    "subscription_id": str(subscription.id),
                    "user_id": str(user.id),
                    "plan_id": str(subscription.plan_id)
                }
            )

            # Send suspension email
            try:
                from src.services.billing_email_service import BillingEmailService

                # Calculate outstanding amount
                plan_name = plan.name if plan else "Unknown Plan"
                if subscription.billing_period.value == "monthly":
                    amount_cents = plan.price_monthly if plan else 0
                else:
                    amount_cents = plan.price_yearly if plan else 0
                amount = f"${amount_cents / 100:.2f}" if amount_cents else "N/A"

                # Format suspension date
                suspension_date = now.strftime("%B %d, %Y")

                # Send email
                email_service = BillingEmailService(self.db)
                await email_service.send_subscription_suspended_email(
                    user_id=user.id,
                    plan_name=plan_name,
                    amount=amount,
                    suspension_date=suspension_date
                )

                logger.info(
                    f"Sent suspension email to {user.email}",
                    extra={
                        "user_id": str(user.id),
                        "subscription_id": str(subscription.id)
                    }
                )

            except Exception as e:
                # Log error but don't fail the suspension
                logger.error(
                    f"Failed to send suspension email: {str(e)}",
                    extra={
                        "user_id": str(user.id),
                        "subscription_id": str(subscription.id),
                        "error": str(e)
                    },
                    exc_info=True
                )

            return True

        except Exception as e:
            logger.error(
                f"Failed to suspend subscription {subscription.id}: {str(e)}",
                extra={
                    "subscription_id": str(subscription.id),
                    "error": str(e)
                },
                exc_info=True
            )
            return False

    async def process_grace_period_expirations(self) -> Dict[str, int]:
        """
        Process all subscriptions with expired grace periods.

        Returns:
            Dict with processing stats
        """
        logger.info("Processing grace period expirations...")

        # Get subscriptions with expired grace periods
        subscriptions = await self.get_expired_grace_periods()

        suspended_count = 0
        failed_count = 0

        # Suspend each subscription
        for subscription in subscriptions:
            try:
                success = await self.suspend_subscription(subscription)

                if success:
                    suspended_count += 1
                else:
                    failed_count += 1

            except Exception as e:
                logger.error(
                    f"Error processing grace period expiration for subscription {subscription.id}: {str(e)}",
                    extra={
                        "subscription_id": str(subscription.id),
                        "error": str(e)
                    }
                )
                failed_count += 1

        logger.info(
            f"Completed grace period processing: {suspended_count} suspended, {failed_count} failed",
            extra={
                "suspended": suspended_count,
                "failed": failed_count,
                "total": len(subscriptions)
            }
        )

        return {
            "total_subscriptions": len(subscriptions),
            "suspended": suspended_count,
            "failed": failed_count
        }
