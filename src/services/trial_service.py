"""
Trial management service.

Handles trial expiration, reminders, conversions, and extensions.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.api.middleware.exceptions import ResourceNotFoundException
from src.api.middleware.exceptions import RextValidationException as ValidationException
from src.api.models.subscription_models.subscriptions import SubscriptionStatus, UserSubscription
from src.api.models.subscription_models.trial_conversions import TrialConversion
from src.api.models.user_models.users import Users
from src.utils.logger import logger


class TrialService:
    """Service for managing trials and conversions."""

    def __init__(self, db: AsyncSession):
        """Initialize trial service."""
        self.db = db

    async def get_expiring_trials(self, days_until_expiry: int) -> List[UserSubscription]:
        """
        Get trials expiring in N days.

        Args:
            days_until_expiry: Number of days until trial expires (e.g., 3, 1, 0)

        Returns:
            List of subscriptions with trials expiring in N days
        """
        target_date = datetime.now(timezone.utc) + timedelta(days=days_until_expiry)
        start_of_day = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_day = start_of_day + timedelta(days=1)

        query = (
            select(UserSubscription)
            .options(
                selectinload(UserSubscription.user).selectinload(Users.notification_preferences),
                selectinload(UserSubscription.plan),
            )
            .where(
                and_(
                    UserSubscription.status == SubscriptionStatus.TRIAL,
                    UserSubscription.trial_end_date >= start_of_day,
                    UserSubscription.trial_end_date < end_of_day,
                )
            )
        )

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def get_expired_trials(self) -> List[UserSubscription]:
        """
        Get trials that have expired but status hasn't been updated.

        Returns:
            List of expired trial subscriptions
        """
        now = datetime.now(timezone.utc)

        query = (
            select(UserSubscription)
            .options(
                selectinload(UserSubscription.user).selectinload(Users.notification_preferences),
                selectinload(UserSubscription.plan),
            )
            .where(
                and_(
                    UserSubscription.status == SubscriptionStatus.TRIAL,
                    UserSubscription.trial_end_date < now,
                )
            )
        )

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def expire_trial(self, subscription_id: UUID) -> UserSubscription:
        """
        Mark a trial as expired.

        Args:
            subscription_id: UUID of the subscription

        Returns:
            Updated subscription

        Raises:
            ResourceNotFoundException: If subscription not found
            ValidationException: If subscription is not a trial
        """
        # Get subscription
        query = select(UserSubscription).where(UserSubscription.id == subscription_id)
        result = await self.db.execute(query)
        subscription = result.scalar_one_or_none()

        if not subscription:
            raise ResourceNotFoundException(
                resource_type="Subscription",
                resource_id=str(subscription_id),
                message="Subscription not found",
            )

        if subscription.status != SubscriptionStatus.TRIAL:
            raise ValidationException(
                message="Subscription is not a trial",
                field="status",
                details={"current_status": subscription.status.value},
            )

        # Update to expired
        subscription.status = SubscriptionStatus.EXPIRED
        subscription.end_date = datetime.now(timezone.utc)
        subscription.updated_at = datetime.now(timezone.utc)

        await self.db.flush()
        await self.db.refresh(subscription)

        logger.info(
            f"Trial expired for subscription {subscription_id}",
            extra={"subscription_id": str(subscription_id), "user_id": str(subscription.user_id)},
        )

        return subscription

    async def track_trial_conversion(
        self,
        user_id: UUID,
        subscription_id: UUID,
        trial_started_at: datetime,
        trial_ended_at: datetime,
        plan_id: UUID,
        billing_period: str,
        payment_amount: Optional[Decimal] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> TrialConversion:
        """
        Track when a trial converts to a paid subscription.

        Args:
            user_id: User who converted
            subscription_id: Subscription that converted
            trial_started_at: When trial started
            trial_ended_at: When trial ended
            plan_id: Plan user converted to
            billing_period: Billing period (monthly/yearly)
            payment_amount: First payment amount
            metadata: Additional conversion data

        Returns:
            Created trial conversion record
        """
        # Calculate trial duration
        duration = (trial_ended_at - trial_started_at).days

        conversion = TrialConversion(
            user_id=user_id,
            subscription_id=subscription_id,
            trial_started_at=trial_started_at,
            trial_ended_at=trial_ended_at,
            converted_at=datetime.now(timezone.utc),
            trial_duration_days=duration,
            conversion_plan_id=plan_id,
            conversion_billing_period=billing_period,
            conversion_amount=payment_amount,
            conversion_metadata=metadata or {},
        )

        self.db.add(conversion)
        await self.db.flush()
        await self.db.refresh(conversion)

        logger.info(
            f"Trial conversion tracked for user {user_id}",
            extra={
                "user_id": str(user_id),
                "subscription_id": str(subscription_id),
                "trial_duration_days": duration,
                "plan_id": str(plan_id),
            },
        )

        return conversion

    async def extend_trial(
        self,
        subscription_id: UUID,
        extension_days: int,
        admin_user_id: UUID,
        reason: Optional[str] = None,
    ) -> UserSubscription:
        """
        Extend a trial period (admin only).

        Args:
            subscription_id: UUID of the subscription
            extension_days: Number of days to extend
            admin_user_id: Admin user performing the extension
            reason: Optional reason for extension

        Returns:
            Updated subscription

        Raises:
            ResourceNotFoundException: If subscription not found
            ValidationException: If subscription is not a trial or extension invalid
        """
        # Get subscription
        query = select(UserSubscription).where(UserSubscription.id == subscription_id)
        result = await self.db.execute(query)
        subscription = result.scalar_one_or_none()

        if not subscription:
            raise ResourceNotFoundException(
                resource_type="Subscription",
                resource_id=str(subscription_id),
                message="Subscription not found",
            )

        if subscription.status != SubscriptionStatus.TRIAL:
            raise ValidationException(
                message="Subscription is not a trial",
                field="status",
                details={"current_status": subscription.status.value},
            )

        if extension_days <= 0 or extension_days > 90:
            raise ValidationException(
                message="Extension must be between 1 and 90 days",
                field="extension_days",
                details={"provided": extension_days},
            )

        # Extend trial
        old_trial_end = subscription.trial_end_date
        base_date = subscription.trial_end_date or datetime.now(timezone.utc)
        subscription.trial_end_date = base_date + timedelta(days=extension_days)
        subscription.updated_at = datetime.now(timezone.utc)

        # Track in metadata
        if not subscription.subscription_metadata:
            subscription.subscription_metadata = {}

        if "trial_extensions" not in subscription.subscription_metadata:
            subscription.subscription_metadata["trial_extensions"] = []

        subscription.subscription_metadata["trial_extensions"].append(
            {
                "extended_by": str(admin_user_id),
                "extension_days": extension_days,
                "old_end_date": old_trial_end.isoformat() if old_trial_end else None,
                "new_end_date": subscription.trial_end_date.isoformat(),
                "reason": reason,
                "extended_at": datetime.now(timezone.utc).isoformat(),
            }
        )

        await self.db.flush()
        await self.db.refresh(subscription)

        logger.info(
            f"Trial extended for subscription {subscription_id}",
            extra={
                "subscription_id": str(subscription_id),
                "user_id": str(subscription.user_id),
                "extension_days": extension_days,
                "admin_user_id": str(admin_user_id),
                "reason": reason,
            },
        )

        return subscription

    async def get_trial_conversion_stats(
        self, start_date: Optional[datetime] = None, end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Get trial conversion statistics for analytics.

        Args:
            start_date: Optional start date for filtering
            end_date: Optional end date for filtering

        Returns:
            Dictionary with conversion statistics
        """
        # Build query
        query = select(TrialConversion)

        if start_date:
            query = query.where(TrialConversion.converted_at >= start_date)
        if end_date:
            query = query.where(TrialConversion.converted_at <= end_date)

        result = await self.db.execute(query)
        conversions = list(result.scalars().all())

        # Calculate stats
        total_conversions = len(conversions)
        if total_conversions == 0:
            return {
                "total_conversions": 0,
                "average_trial_duration": 0,
                "average_conversion_time": 0,
                "total_revenue": Decimal("0.00"),
                "conversion_by_period": {},
            }

        avg_trial_duration = sum(c.trial_duration_days for c in conversions) / total_conversions
        avg_conversion_time = sum(c.conversion_rate_days for c in conversions) / total_conversions

        total_revenue = sum(
            c.conversion_amount for c in conversions if c.conversion_amount
        ) or Decimal("0.00")

        # Group by billing period
        by_period = {}
        for conversion in conversions:
            period = conversion.conversion_billing_period
            if period not in by_period:
                by_period[period] = 0
            by_period[period] += 1

        return {
            "total_conversions": total_conversions,
            "average_trial_duration": round(avg_trial_duration, 2),
            "average_conversion_time": round(avg_conversion_time, 2),
            "total_revenue": float(total_revenue),
            "conversion_by_period": by_period,
            "date_range": {
                "start": start_date.isoformat() if start_date else None,
                "end": end_date.isoformat() if end_date else None,
            },
        }

    async def check_trial_eligibility(self, user_id: UUID) -> Dict[str, Any]:
        """
        Check if user is eligible for a trial.

        Args:
            user_id: User to check

        Returns:
            Dictionary with eligibility info
        """
        # Check if user has had a trial before
        query = select(UserSubscription).where(
            and_(
                UserSubscription.user_id == user_id,
                or_(
                    UserSubscription.status == SubscriptionStatus.TRIAL,
                    UserSubscription.trial_end_date.isnot(None),
                ),
            )
        )

        result = await self.db.execute(query)
        subscriptions = list(result.scalars().all())

        has_active_trial = any(s.status == SubscriptionStatus.TRIAL for s in subscriptions)
        has_previous_trial = len(subscriptions) > 0

        return {
            "eligible": not has_previous_trial,
            "has_active_trial": has_active_trial,
            "has_previous_trial": has_previous_trial,
            "previous_trials_count": len(subscriptions),
            "reason": None if not has_previous_trial else "User has already used a trial period",
        }
