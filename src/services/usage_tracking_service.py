"""
Usage Tracking Service

This service tracks and manages usage metrics for users based on their subscription plan.
It calculates current usage against plan limits and provides real-time usage data.
"""

from typing import Dict, Any, Tuple, Optional
from uuid import UUID
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from sqlalchemy.orm import selectinload

from src.api.models.subscription_models.subscriptions import UserSubscription, SubscriptionStatus
from src.api.models.subscription_models.plans import SubscriptionPlan
from src.api.models.workspace_models.workspace_model import WorkspaceModel
from src.api.models.workspace_models.workspace_member import WorkspaceMembers
from src.api.models.knowledge_models.knowledge_model import (
    KnowledgeFiles,
    TextKnowledge,
    Website
)
from src.utils.logger import logger


class UsageTrackingService:
    """Service for tracking and managing user usage metrics"""

    def __init__(self, db: AsyncSession):
        """Initialize usage tracking service"""
        self.db = db

    async def get_usage_metrics(self, user_id: UUID) -> Dict[str, Any]:
        """
        Get current usage metrics for a user.

        Args:
            user_id: User UUID

        Returns:
            Dictionary with usage metrics for each resource type:
            {
                "workspaces": {"used": 3, "limit": 10, "percentage": 30},
                "members": {"used": 15, "limit": 50, "percentage": 30},
                "topics": {"used": 45, "limit": 100, "percentage": 45},
                "knowledge_items": {"used": 230, "limit": 1000, "percentage": 23},
                "api_calls": {"used": 450, "limit": 10000, "percentage": 4.5, "reset_date": "2025-11-12"}
            }
        """
        # Get user's active subscription with plan eagerly loaded
        subscription_query = select(UserSubscription).options(
            selectinload(UserSubscription.plan)
        ).where(
            and_(
                UserSubscription.user_id == user_id,
                UserSubscription.status.in_([SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL])
            )
        )
        result = await self.db.execute(subscription_query)
        subscription = result.scalar_one_or_none()

        # If no subscription, return free tier usage
        if not subscription or not subscription.plan:
            return await self._get_free_tier_usage(user_id)

        plan = subscription.plan

        # Count workspaces owned by user
        workspace_count_query = select(func.count(WorkspaceModel.id)).where(
            WorkspaceModel.user_id == user_id
        )
        workspace_count_result = await self.db.execute(workspace_count_query)
        workspace_count = workspace_count_result.scalar() or 0

        # Count total members across all user's workspaces
        member_count_query = select(func.count(WorkspaceMembers.id)).join(
            WorkspaceModel
        ).where(
            WorkspaceModel.user_id == user_id
        )
        member_count_result = await self.db.execute(member_count_query)
        member_count = member_count_result.scalar() or 0

        # Count knowledge items
        knowledge_count = await self._count_knowledge_items(user_id)

        # Get API calls this month
        api_calls = subscription.current_api_calls or 0

        usage_data = {
            "subscription_id": str(subscription.id),
            "plan_name": plan.name if plan else "Unknown",
            "billing_period": subscription.billing_period.value,
            "current_workspaces": workspace_count,
            "current_knowledge_items": knowledge_count,
            "current_api_calls": subscription.current_api_calls,
            "max_workspaces": plan.max_workspaces if plan else 0,
            "max_knowledge_items": plan.max_knowledge_items if plan else 0,
            "max_api_calls_per_month": plan.max_api_calls_per_month if plan else 0,
            "workspaces_usage_percent": self._calc_percentage(workspace_count, plan.max_workspaces if plan else 0),
            "knowledge_items_usage_percent": self._calc_percentage(knowledge_count, plan.max_knowledge_items if plan else 0),
            "api_calls_usage_percent": self._calc_percentage(api_calls, plan.max_api_calls_per_month if plan else 0),
            "usage_reset_date": subscription.usage_reset_date.isoformat() if subscription.usage_reset_date else None
        }

        return usage_data


    async def check_limit(
        self,
        user_id: UUID,
        limit_type: str
    ) -> Tuple[bool, int, Optional[int]]:
        """
        Check if user has exceeded a specific limit.

        Args:
            user_id: User UUID
            limit_type: Type of limit to check (workspaces, members, topics, knowledge_items, api_calls)

        Returns:
            Tuple of (within_limit, used, limit)
            - within_limit: True if under limit, False if at or over limit
            - used: Current usage count
            - limit: Limit value (None if unlimited)
        """
        usage = await self.get_usage_metrics(user_id)
        limit_data = usage.get(limit_type)

        if not limit_data:
            logger.warning(f"Unknown limit type: {limit_type}")
            return (True, 0, None)

        # Check if unlimited
        if limit_data.get("unlimited", False):
            return (True, limit_data["used"], None)

        used = limit_data["used"]
        limit = limit_data["limit"]

        # Within limit if usage is less than limit
        within_limit = used < limit if limit is not None else True

        return (within_limit, used, limit)

    async def increment_api_calls(self, user_id: UUID) -> None:
        """
        Increment API call counter for user's subscription.

        Args:
            user_id: User UUID
        """
        subscription_query = select(UserSubscription).where(
            and_(
                UserSubscription.user_id == user_id,
                UserSubscription.status.in_([SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL])
            )
        )
        result = await self.db.execute(subscription_query)
        subscription = result.scalar_one_or_none()

        if subscription:
            subscription.current_api_calls = (subscription.current_api_calls or 0) + 1
            await self.db.flush()
            logger.debug(f"Incremented API calls for user {user_id}: {subscription.current_api_calls}")

    async def reset_monthly_usage(self, user_id: UUID) -> None:
        """
        Reset monthly usage counters (called by scheduled job).

        Args:
            user_id: User UUID
        """
        subscription_query = select(UserSubscription).where(
            UserSubscription.user_id == user_id
        )
        result = await self.db.execute(subscription_query)
        subscription = result.scalar_one_or_none()

        if subscription:
            subscription.current_api_calls = 0
            subscription.usage_reset_date = datetime.now(timezone.utc) + timedelta(days=30)
            await self.db.flush()
            logger.info(f"Reset monthly usage for user {user_id}")

    async def _count_knowledge_items(self, user_id: UUID) -> int:
        """Count total knowledge items across all types for user's workspaces"""
        # Knowledge files
        files_query = select(func.count(KnowledgeFiles.id)).join(
            WorkspaceModel
        ).where(
            WorkspaceModel.user_id == user_id
        )
        files_result = await self.db.execute(files_query)
        files_count = files_result.scalar() or 0

        # Text knowledge
        text_query = select(func.count(TextKnowledge.id)).join(
            WorkspaceModel
        ).where(
            WorkspaceModel.user_id == user_id
        )
        text_result = await self.db.execute(text_query)
        text_count = text_result.scalar() or 0

        # Website knowledge
        website_query = select(func.count(Website.id)).join(
            WorkspaceModel
        ).where(
            WorkspaceModel.user_id == user_id
        )
        website_result = await self.db.execute(website_query)
        website_count = website_result.scalar() or 0

        return files_count + text_count + website_count

    def _calc_percentage(self, used: int, limit: Optional[int]) -> float:
        """Calculate usage percentage"""
        if limit is None or limit <= 0:
            return 0.0
        return min(round((used / limit) * 100, 1), 100.0)

    async def _get_free_tier_usage(self, user_id: UUID) -> Dict[str, Any]:
        """
        Get usage for free tier (no active subscription).
        Returns actual counts with None/0 limits to indicate free tier restrictions.
        """
        # Count workspaces
        workspace_count_query = select(func.count(WorkspaceModel.id)).where(
            WorkspaceModel.user_id == user_id
        )
        workspace_count_result = await self.db.execute(workspace_count_query)
        workspace_count = workspace_count_result.scalar() or 0

        # Count members
        member_count_query = select(func.count(WorkspaceMembers.id)).join(
            WorkspaceModel
        ).where(
            WorkspaceModel.user_id == user_id
        )
        member_count_result = await self.db.execute(member_count_query)
        member_count = member_count_result.scalar() or 0

        # Count knowledge items
        knowledge_count = await self._count_knowledge_items(user_id)

        # Free tier limits
        free_max_workspaces = 1
        free_max_knowledge_items = 50
        free_max_api_calls = 100

        usage_data = {
            "subscription_id": None,
            "plan_name": "Free",
            "billing_period": None,
            "current_workspaces": workspace_count,
            "current_knowledge_items": knowledge_count,
            "current_api_calls": 0,
            "max_workspaces": free_max_workspaces,
            "max_knowledge_items": free_max_knowledge_items,
            "max_api_calls_per_month": free_max_api_calls,
            "workspaces_usage_percent": self._calc_percentage(workspace_count, free_max_workspaces),
            "knowledge_items_usage_percent": self._calc_percentage(knowledge_count, free_max_knowledge_items),
            "api_calls_usage_percent": 0.0,
            "usage_reset_date": None
        }

        return usage_data
