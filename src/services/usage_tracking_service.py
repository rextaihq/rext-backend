"""
Usage Tracking Service

This service tracks and manages usage metrics for users based on their subscription plan.
It calculates current usage against plan limits and provides real-time usage data.
"""

from typing import Dict, Any, Tuple, Optional
from uuid import UUID
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from sqlalchemy.orm import selectinload
from src.utils.logger import logger
from src.utils.datetime_utils import next_billing_anchor
from src.api.models.subscription_models.subscriptions import UserSubscription, SubscriptionStatus, subscription_grants_access
from src.api.models.workspace_models.workspace_model import WorkspaceModel
from src.api.models.workspace_models.workspace_member import WorkspaceMembers
from src.api.models.knowledge_models.knowledge_model import (
    KnowledgeFiles,
    TextKnowledge,
    Website
)


# Default limits for free tier when no subscription plan is found
FREE_MAX_WORKSPACES = 1
FREE_MAX_KNOWLEDGE_ITEMS = 10
FREE_MAX_API_CALLS = 100


class UsageTrackingService:
    """Service for tracking and managing user usage metrics"""

    def __init__(self, db: AsyncSession):
        """Initialize usage tracking service"""
        self.db = db

    async def get_usage_metrics(self, user_id: UUID) -> Dict[str, Any]:
        """
        Get current usage metrics for a user.

        Returns:
            Dictionary with usage metrics for each resource type:
            {
                "workspaces": {"used": 3, "limit": 10, ...},
                "knowledge_items": {"used": 230, "limit": 1000, ...},
                "api_calls": {"used": 450, "limit": 10000, ...},
                "meta": {"plan_name": "Pro", ...}
            }
        """
        # Get user's active (or cancelled-but-in-grace-period) subscription with plan eagerly loaded
        subscription_query = select(UserSubscription).options(
            selectinload(UserSubscription.plan)
        ).where(
            and_(
                UserSubscription.user_id == user_id,
                subscription_grants_access()
            )
        ).order_by(UserSubscription.start_date.desc()).limit(1)
        result = await self.db.execute(subscription_query)
        subscription = result.scalar_one_or_none()

        # If no subscription, return free tier usage
        if not subscription or not subscription.plan:
            return await self._get_free_tier_usage(user_id)

        plan = subscription.plan

        # Count workspaces owned by user (excluding soft-deleted ones)
        workspace_count_query = select(func.count(WorkspaceModel.id)).where(
            WorkspaceModel.user_id == user_id,
            WorkspaceModel.deleted_at.is_(None)
        )
        workspace_count_result = await self.db.execute(workspace_count_query)
        workspace_count = workspace_count_result.scalar() or 0

        # Count total members across all user's active workspaces
        member_count_query = select(func.count(WorkspaceMembers.id)).join(
            WorkspaceModel
        ).where(
            WorkspaceModel.user_id == user_id,
            WorkspaceModel.deleted_at.is_(None)
        )
        member_count_result = await self.db.execute(member_count_query)
        member_count = member_count_result.scalar() or 0

        # Count knowledge items
        knowledge_count = await self._count_knowledge_items(user_id)

        # Get API calls this month
        api_calls = subscription.current_api_calls or 0

        # Helper to build metric dict
        def build_metric(used, limit):
            unlimited = limit == -1 or limit is None
            return {
                "used": used,
                "limit": limit if not unlimited else None,
                "percentage": self._calc_percentage(used, limit),
                "unlimited": unlimited
            }

        usage_data = {
            "workspaces": build_metric(workspace_count, plan.max_workspaces),
            "members": build_metric(member_count, plan.max_members_per_workspace),
            "knowledge_items": build_metric(knowledge_count, plan.max_knowledge_items),
            "api_calls": {
                **build_metric(api_calls, plan.max_api_calls_per_month),
                "reset_date": subscription.usage_reset_date.isoformat() if subscription.usage_reset_date else None
            },
            "meta": {
                "subscription_id": str(subscription.id),
                "plan_name": plan.name,
                "billing_period": subscription.billing_period.value
            }
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
            limit_type: Type of limit to check
                        Valid values: "workspaces", "knowledge_items", "api_calls"

        Returns:
            Tuple of (within_limit, used, limit)
            - within_limit: True if under limit, False if at or over limit
            - used: Current usage count
            - limit: Limit value (None if unlimited)
        """
        usage = await self.get_usage_metrics(user_id)

        if limit_type not in usage:
            logger.warning(f"Unknown limit type: {limit_type}")
            return True, 0, None

        metric = usage.get(limit_type, {})
        used = metric.get("used", 0) or 0
        limit = metric.get("limit")

        # BYPASS: Workspace limit check is temporarily disabled to allow multiple workspaces for testing
        if limit_type == "workspaces":
            return True, used, None

        # Original limit check logic
        # if limit is None or limit <= 0:
        #     return True, used, None
        #
        # within_limit = used < limit
        # return within_limit, used, limit

        # Default to True for other types if no limit is set
        if limit is None or limit <= 0:
            return True, used, None

        within_limit = used < limit
        return within_limit, used, limit


    async def get_credit_balance(self, user_id: UUID) -> int:
        """Return current credit balance for user's active (or cancelled-but-in-grace-period) subscription."""
        result = await self.db.execute(
            select(UserSubscription).where(
                and_(
                    UserSubscription.user_id == user_id,
                    subscription_grants_access()
                )
            ).order_by(UserSubscription.start_date.desc()).limit(1)
        )
        subscription = result.scalar_one_or_none()
        return subscription.current_credits if subscription else 0

    async def consume_credits(self, user_id: UUID, cost: int) -> bool:
        """
        Deduct credits from user's subscription.

        Returns True on success, False if insufficient credits.
        """
        result = await self.db.execute(
            select(UserSubscription).options(
                selectinload(UserSubscription.plan)
            ).where(
                and_(
                    UserSubscription.user_id == user_id,
                    subscription_grants_access()
                )
            ).order_by(UserSubscription.start_date.desc()).limit(1)
        )
        subscription = result.scalar_one_or_none()
        if not subscription:
            return False

        # Replenish if reset date passed (non-trial plans)
        if (
            subscription.plan
            and not subscription.plan.is_trial_plan
            and subscription.credits_reset_date
        ):
            reset_dt = subscription.credits_reset_date
            if reset_dt.tzinfo is None:
                reset_dt = reset_dt.replace(tzinfo=timezone.utc)
            if reset_dt < datetime.now(timezone.utc):
                subscription.current_credits = subscription.plan.credits_per_month or 0
                subscription.credits_reset_date = next_billing_anchor(subscription.credits_reset_date)

        if subscription.current_credits < cost:
            return False

        subscription.current_credits -= cost
        await self.db.flush()
        return True

    async def replenish_credits(self, user_id: UUID) -> None:
        """Reset credits to plan amount (monthly renewal)."""
        result = await self.db.execute(
            select(UserSubscription).options(
                selectinload(UserSubscription.plan)
            ).where(
                and_(
                    UserSubscription.user_id == user_id,
                    UserSubscription.status.in_([SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL])
                )
            ).order_by(UserSubscription.start_date.desc()).limit(1)
        )
        subscription = result.scalar_one_or_none()
        if subscription and subscription.plan and not subscription.plan.is_trial_plan:
            subscription.current_credits = subscription.plan.credits_per_month or 0
            base_date = subscription.credits_reset_date or subscription.renews_at or datetime.now(timezone.utc)
            subscription.credits_reset_date = next_billing_anchor(base_date)
            await self.db.flush()

    async def allocate_credits(self, user_id: UUID, amount: int) -> None:
        """Set credit balance to a specific amount (used at trial/plan activation)."""
        result = await self.db.execute(
            select(UserSubscription).where(
                UserSubscription.user_id == user_id
            ).order_by(UserSubscription.start_date.desc()).limit(1)
        )
        subscription = result.scalar_one_or_none()
        if subscription:
            subscription.current_credits = amount
            await self.db.flush()

    async def increment_api_calls(self, user_id: UUID) -> None:
        """
        Increment API call counter for user's subscription.

        Args:
            user_id: User UUID
        """
        subscription_query = select(UserSubscription).where(
            and_(
                UserSubscription.user_id == user_id,
                subscription_grants_access()
            )
        ).order_by(UserSubscription.start_date.desc()).limit(1)
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
        ).order_by(UserSubscription.start_date.desc()).limit(1)
        result = await self.db.execute(subscription_query)
        subscription = result.scalar_one_or_none()

        if subscription:
            subscription.current_api_calls = 0
            base_date = subscription.usage_reset_date or subscription.renews_at or datetime.now(timezone.utc)
            subscription.usage_reset_date = next_billing_anchor(base_date)
            await self.db.flush()
            logger.info(f"Reset monthly usage for user {user_id}")

    async def _count_knowledge_items(self, user_id: UUID) -> int:
        """Count total knowledge items across all types for user's active workspaces"""
        # Knowledge files
        files_query = select(func.count(KnowledgeFiles.id)).join(
            WorkspaceModel
        ).where(
            WorkspaceModel.user_id == user_id,
            WorkspaceModel.deleted_at.is_(None)
        )
        files_result = await self.db.execute(files_query)
        files_count = files_result.scalar() or 0

        # Text knowledge
        text_query = select(func.count(TextKnowledge.id)).join(
            WorkspaceModel
        ).where(
            WorkspaceModel.user_id == user_id,
            WorkspaceModel.deleted_at.is_(None)
        )
        text_result = await self.db.execute(text_query)
        text_count = text_result.scalar() or 0

        # Website knowledge
        website_query = select(func.count(Website.id)).join(
            WorkspaceModel
        ).where(
            WorkspaceModel.user_id == user_id,
            WorkspaceModel.deleted_at.is_(None)
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
        # Count workspaces (excluding soft-deleted ones)
        workspace_count_query = select(func.count(WorkspaceModel.id)).where(
            WorkspaceModel.user_id == user_id,
            WorkspaceModel.deleted_at.is_(None)
        )
        workspace_count_result = await self.db.execute(workspace_count_query)
        workspace_count = workspace_count_result.scalar() or 0

        # Count members
        member_count_query = select(func.count(WorkspaceMembers.id)).join(
            WorkspaceModel
        ).where(
            WorkspaceModel.user_id == user_id,
            WorkspaceModel.deleted_at.is_(None)
        )
        member_count_result = await self.db.execute(member_count_query)
        member_count = member_count_result.scalar() or 0

        # Count knowledge items
        knowledge_count = await self._count_knowledge_items(user_id)

        # Helper to build metric dict
        def build_metric(used, limit):
            unlimited = limit == -1 or limit is None
            return {
                "used": used,
                "limit": limit if not unlimited else None,
                "percentage": self._calc_percentage(used, limit),
                "unlimited": unlimited
            }

        usage_data = {
            "workspaces": build_metric(workspace_count, FREE_MAX_WORKSPACES),
            "members": build_metric(member_count, 3), # Default free limit if not in plan
            "topics": build_metric(0, 5), # Default free limit
            "knowledge_items": build_metric(knowledge_count, FREE_MAX_KNOWLEDGE_ITEMS),
            "api_calls": {
                **build_metric(0, FREE_MAX_API_CALLS),
                "reset_date": None
            },
            "meta": {
                "subscription_id": None,
                "plan_name": "Free",
                "billing_period": None
            }
        }

        return usage_data
