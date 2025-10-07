"""Business logic for administrative subscription management operations."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.middleware.exceptions import (
    DuplicateResourceException,
    ResourceNotFoundException,
)
from src.api.models.subscription_models.plans import SubscriptionPlan
from src.api.models.subscription_models.subscriptions import (
    SubscriptionStatus,
    UserSubscription,
)
from src.api.models.user_models.users import Users
from src.api.schema.subscription import (
    AdminSubscriptionAssignRequest,
    AdminSubscriptionExtendRequest,
    AdminUsageResetRequest,
)
from src.utils.logger import logger


class SubscriptionManagementService:
    """Encapsulate manual subscription management actions for administrators."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def assign_subscription(
        self,
        admin_user_id: UUID,
        payload: AdminSubscriptionAssignRequest,
    ) -> Dict[str, Any]:
        user = await self._get_user_or_404(payload.user_id)
        plan = await self._get_active_plan(payload.plan_id)

        await self._ensure_no_active_subscription(payload.user_id)

        trial_end = None
        if payload.trial_days and payload.trial_days > 0:
            trial_end = datetime.utcnow() + timedelta(days=payload.trial_days)

        subscription = UserSubscription(
            user_id=payload.user_id,
            plan_id=payload.plan_id,
            status=payload.status,
            billing_period=payload.billing_period,
            start_date=datetime.utcnow(),
            trial_end_date=trial_end,
            current_api_calls=0,
            usage_reset_date=datetime.utcnow() + timedelta(days=30),
            subscription_metadata={"assigned_by_admin": str(admin_user_id)},
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )

        self.db.add(subscription)
        await self.db.flush()
        await self.db.refresh(subscription)

        logger.info(
            "Subscription manually assigned",
            extra={
                "admin_user_id": str(admin_user_id),
                "target_user_id": str(payload.user_id),
                "plan_id": str(payload.plan_id),
                "status": payload.status.value if isinstance(payload.status, SubscriptionStatus) else payload.status,
            },
        )

        response = subscription.to_dict()
        response["plan_name"] = plan.name
        response["plan_display_name"] = plan.display_name
        response["user_username"] = user.username
        response["user_email"] = user.email
        return {
            "subscription": response,
            "message": f"Successfully assigned {plan.display_name} to user {user.username}",
        }

    async def extend_subscription(
        self,
        admin_user_id: UUID,
        subscription_id: UUID,
        payload: AdminSubscriptionExtendRequest,
    ) -> Dict[str, Any]:
        subscription = await self._get_subscription_or_404(subscription_id)

        if subscription.end_date:
            subscription.end_date = subscription.end_date + timedelta(days=payload.extend_days)
        else:
            subscription.end_date = datetime.utcnow() + timedelta(days=payload.extend_days)

        if subscription.status == SubscriptionStatus.TRIAL and subscription.trial_end_date:
            subscription.trial_end_date = subscription.trial_end_date + timedelta(days=payload.extend_days)

        subscription.updated_at = datetime.utcnow()
        await self.db.flush()
        await self.db.refresh(subscription)

        logger.info(
            "Subscription extended",
            extra={
                "admin_user_id": str(admin_user_id),
                "subscription_id": str(subscription_id),
                "extend_days": payload.extend_days,
            },
        )

        return {
            "subscription": subscription.to_dict(),
            "message": f"Subscription extended by {payload.extend_days} days",
        }

    async def reset_usage(
        self,
        admin_user_id: UUID,
        subscription_id: UUID,
        payload: AdminUsageResetRequest,
    ) -> Dict[str, Any]:
        subscription = await self._get_subscription_or_404(subscription_id)
        old_api_calls = subscription.current_api_calls

        if payload.reset_api_calls:
            subscription.current_api_calls = 0
            subscription.usage_reset_date = datetime.utcnow() + timedelta(days=30)

        subscription.updated_at = datetime.utcnow()
        await self.db.flush()
        await self.db.refresh(subscription)

        logger.info(
            "Subscription usage reset",
            extra={
                "admin_user_id": str(admin_user_id),
                "subscription_id": str(subscription_id),
                "old_api_calls": old_api_calls,
            },
        )

        return {
            "subscription": subscription.to_dict(),
            "message": "Usage counters reset successfully",
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _get_user_or_404(self, user_id: UUID) -> Users:
        result = await self.db.execute(select(Users).where(Users.id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            raise ResourceNotFoundException(resource_type="user", resource_id=str(user_id))
        return user

    async def _get_active_plan(self, plan_id: UUID) -> SubscriptionPlan:
        result = await self.db.execute(
            select(SubscriptionPlan).where(
                SubscriptionPlan.id == plan_id,
                SubscriptionPlan.is_active.is_(True),
            )
        )
        plan = result.scalar_one_or_none()
        if not plan:
            raise ResourceNotFoundException(resource_type="subscription_plan", resource_id=str(plan_id))
        return plan

    async def _ensure_no_active_subscription(self, user_id: UUID) -> None:
        result = await self.db.execute(
            select(UserSubscription).where(
                UserSubscription.user_id == user_id,
                UserSubscription.status.in_([SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL]),
            )
        )
        if result.scalar_one_or_none():
            raise DuplicateResourceException(
                resource_type="subscription",
                conflicting_field="user_id",
                conflicting_value=str(user_id),
                message="User already has an active or trial subscription",
            )

    async def _get_subscription_or_404(self, subscription_id: UUID) -> UserSubscription:
        result = await self.db.execute(
            select(UserSubscription).where(UserSubscription.id == subscription_id)
        )
        subscription = result.scalar_one_or_none()
        if not subscription:
            raise ResourceNotFoundException(resource_type="subscription", resource_id=str(subscription_id))
        return subscription
