"""Service encapsulating subscription plan administration logic."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.middleware.exceptions import (
    DuplicateResourceException,
    ResourceNotFoundException,
    RextAuthorizationException,
    RextValidationException,
)
from src.api.cache.decorators import cached, invalidate_cache
from src.api.models.subscription_models.plans import SubscriptionPlan
from src.api.models.subscription_models.subscriptions import SubscriptionStatus, UserSubscription
from src.api.models.user_models.roles import Role
from src.api.models.user_models.user_roles import UserRole
from src.api.schema.subscription.plan_schemas import SubscriptionPlanCreate, SubscriptionPlanUpdate
from src.utils.logger import logger


class SubscriptionPlanService:
    """Provide administrative subscription plan operations."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def is_admin(self, user_id: UUID) -> bool:
        result = await self.db.execute(
            select(UserRole)
            .join(Role)
            .where(UserRole.user_id == user_id, Role.name.in_(["admin", "super_admin"]))
        )
        return result.scalar_one_or_none() is not None

    async def require_admin(self, user_id: UUID) -> None:
        if not await self.is_admin(user_id):
            raise RextAuthorizationException(
                message="Admin role required for subscription plan administration",
                required_permission="subscription.admin"
            )

    async def create_plan(self, payload: SubscriptionPlanCreate) -> Dict[str, object]:
        await self._ensure_unique_name(payload.name)

        plan = SubscriptionPlan(
            name=payload.name.lower(),
            display_name=payload.display_name,
            description=payload.description,
            price_monthly=payload.price_monthly,
            price_yearly=payload.price_yearly,
            features=payload.features or {},
            max_workspaces=payload.max_workspaces,
            max_members_per_workspace=payload.max_members_per_workspace,
            max_topics=payload.max_topics,
            max_knowledge_items=payload.max_knowledge_items,
            max_api_calls_per_month=payload.max_api_calls_per_month,
            is_active=payload.is_active,
            is_public=payload.is_public,
            lemonsqueezy_variant_id_monthly=payload.lemonsqueezy_variant_id_monthly,
            lemonsqueezy_variant_id_yearly=payload.lemonsqueezy_variant_id_yearly,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        self.db.add(plan)
        await self.db.flush()
        await self.db.refresh(plan)

        logger.info("Subscription plan created", extra={"plan_id": str(plan.id), "plan_name": plan.name})

        return {
            "plan": plan.to_dict(),
            "message": f"Subscription plan '{plan.display_name}' created successfully",
        }

    @cached(
        key_prefix="subscription:plans",
        ttl=900,
        key_builder=lambda self, include_inactive, include_private, is_admin:
            f"{is_admin}:{include_inactive}:{include_private}",
    )
    async def list_plans(
        self,
        include_inactive: bool,
        include_private: bool,
        is_admin: bool,
    ) -> Dict[str, object]:
        query = select(SubscriptionPlan)

        if not is_admin:
            query = query.where(SubscriptionPlan.is_active.is_(True), SubscriptionPlan.is_public.is_(True))
        else:
            if not include_inactive:
                query = query.where(SubscriptionPlan.is_active.is_(True))
            if not include_private:
                query = query.where(SubscriptionPlan.is_public.is_(True))

        result = await self.db.execute(query.order_by(SubscriptionPlan.price_monthly.asc()))
        plans = result.scalars().all()

        return {
            "plans": [plan.to_dict() for plan in plans],
            "count": len(plans),
        }

    async def get_plan(self, plan_id: UUID, is_admin: bool) -> Dict[str, object]:
        plan = await self._get_plan_or_404(plan_id)

        if not is_admin and (not plan.is_public or not plan.is_active):
            raise ResourceNotFoundException(
                message="Subscription plan not found",
                resource_type="subscription_plan",
                resource_id=str(plan_id)
            )

        plan_data = plan.to_dict()

        if is_admin:
            count_result = await self.db.execute(
                select(func.count(UserSubscription.id)).where(
                    UserSubscription.plan_id == plan_id,
                    UserSubscription.status.in_([SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL]),
                )
            )
            plan_data["active_subscriptions"] = count_result.scalar() or 0

        return plan_data

    async def update_plan(self, plan_id: UUID, payload: SubscriptionPlanUpdate) -> Dict[str, object]:
        plan = await self._get_plan_or_404(plan_id)
        update_data = payload.model_dump(exclude_unset=True)

        if not update_data:
            raise RextValidationException(
                message="No fields provided for update",
                field_errors={"update_data": ["At least one field must be provided"]},
            )

        for field, value in update_data.items():
            setattr(plan, field, value)

        plan.updated_at = datetime.now(timezone.utc)
        await self.db.flush()
        await self.db.refresh(plan)

        await invalidate_cache("subscription:plans:*")
        logger.info("Subscription plan updated", extra={"plan_id": str(plan.id)})

        return plan.to_dict()

    async def delete_plan(self, plan_id: UUID, *, force: bool = False) -> Dict[str, object]:
        plan = await self._get_plan_or_404(plan_id)

        count_result = await self.db.execute(
            select(func.count(UserSubscription.id)).where(
                UserSubscription.plan_id == plan_id,
                UserSubscription.status.in_([SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL]),
            )
        )
        active_subscriptions = count_result.scalar() or 0

        if active_subscriptions > 0 and not force:
            raise RextValidationException(
                message="Cannot delete plan with active subscriptions",
                field_errors={
                    "plan_id": [
                        f"Plan has {active_subscriptions} active subscription(s). Use force=true to override."
                    ]
                },
            )

        plan_name = plan.display_name
        await self.db.delete(plan)
        await self.db.flush()

        await invalidate_cache("subscription:plans:*")
        logger.warning("Subscription plan deleted", extra={"plan_id": str(plan_id), "force": force})

        return {
            "deleted_plan_id": str(plan_id),
            "plan_name": plan_name,
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _get_plan_or_404(self, plan_id: UUID) -> SubscriptionPlan:
        result = await self.db.execute(select(SubscriptionPlan).where(SubscriptionPlan.id == plan_id))
        plan = result.scalar_one_or_none()
        if not plan:
            raise ResourceNotFoundException(resource_type="subscription_plan", resource_id=str(plan_id))
        return plan

    async def _ensure_unique_name(self, name: str) -> None:
        result = await self.db.execute(
            select(SubscriptionPlan).where(func.lower(SubscriptionPlan.name) == name.lower())
        )
        if result.scalar_one_or_none():
            raise DuplicateResourceException(
                resource_type="subscription_plan",
                conflicting_field="name",
                conflicting_value=name,
                message=f"Plan with name '{name}' already exists",
            )
