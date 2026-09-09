"""Administrative subscription retrieval operations."""

from __future__ import annotations

from typing import Any, Dict, Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.middleware.exceptions import ResourceNotFoundException, RextValidationException
from src.api.models.subscription_models.plans import SubscriptionPlan
from src.api.models.subscription_models.subscriptions import SubscriptionStatus, UserSubscription
from src.api.models.user_models.users import Users


class SubscriptionRetrievalService:
    """Provide filtered subscription listings for administrators."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_subscriptions(
        self,
        status_filter: Optional[str],
        plan_id: Optional[UUID],
        user_email: Optional[str],
        limit: int,
        offset: int,
    ) -> Dict[str, Any]:
        query = (
            select(UserSubscription, Users, SubscriptionPlan)
            .join(Users, UserSubscription.user_id == Users.id)
            .join(SubscriptionPlan, UserSubscription.plan_id == SubscriptionPlan.id)
        )

        if status_filter:
            try:
                status_enum = SubscriptionStatus(status_filter.lower())
            except ValueError as exc:
                raise RextValidationException(
                    message=f"Invalid status: {status_filter}",
                    field_errors={"status_filter": ["Unsupported subscription status"]},
                ) from exc
            query = query.where(UserSubscription.status == status_enum)

        if plan_id:
            query = query.where(UserSubscription.plan_id == plan_id)

        if user_email:
            query = query.where(Users.email.ilike(f"%{user_email}%"))

        count_query = select(func.count()).select_from(query.subquery())
        result = await self.db.execute(count_query)
        total = result.scalar() or 0

        result = await self.db.execute(
            query.order_by(UserSubscription.created_at.desc()).offset(offset).limit(limit)
        )
        rows = result.all()

        subscriptions = []
        for subscription, user, plan in rows:
            data = subscription.to_dict()
            data.update(
                {
                    "user_email": user.email,
                    "user_full_name": user.full_name or user.display_name or user.email,
                    "plan_name": plan.name,
                    "plan_display_name": plan.display_name,
                }
            )
            subscriptions.append(data)

        return {
            "data": {
                "subscriptions": subscriptions,
                "total": total,
                "limit": limit,
                "offset": offset,
                "has_more": (offset + limit) < total,
            },
            "message": f"Retrieved {len(subscriptions)} subscription(s)",
        }

    async def get_subscription(self, subscription_id: UUID) -> Dict[str, Any]:
        query = (
            select(UserSubscription, Users, SubscriptionPlan)
            .join(Users, UserSubscription.user_id == Users.id)
            .join(SubscriptionPlan, UserSubscription.plan_id == SubscriptionPlan.id)
            .where(UserSubscription.id == subscription_id)
        )
        result = await self.db.execute(query)
        row = result.first()
        if not row:
            raise ResourceNotFoundException(
                resource_type="subscription", resource_id=str(subscription_id)
            )

        subscription, user, plan = row
        data = subscription.to_dict()
        data["user"] = {
            "id": str(user.id),
            "email": user.email,
            "full_name": user.full_name or user.display_name or user.email,
            "status": user.status,
        }
        data["plan"] = plan.to_dict()

        return {
            "data": data,
            "message": "Subscription details retrieved successfully",
        }
