"""
Usage limit checking middleware for subscription plans.

This module provides dependency injection utilities for checking user's
resource usage against their subscription plan limits before allowing
resource-intensive operations.

Usage:
    from src.api.middleware.usage_limiter import check_workspace_limit, check_api_limit

    @router.post("/workspaces")
    def create_workspace(
        _: None = Depends(check_workspace_limit()),
        db: AsyncSession = Depends(get_db),
        current_user: dict = Depends(get_current_user)
    ):
        # Create workspace...
"""

from typing import Optional
import asyncio
from fastapi import Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select
from datetime import datetime, timedelta

from src.api.database.async_database import get_async_db as get_db
from src.api.security.dependencies import get_current_user
from src.api.models.subscription_models.subscriptions import (
    UserSubscription,
    SubscriptionStatus
)
from src.api.models.subscription_models.plans import SubscriptionPlan
from src.api.models.workspace_models.workspace_model import WorkspaceModel as Workspace
from src.api.models.workspace_models.workspace_member import WorkspaceMembers
from src.api.models.knowledge_models.knowledge_model import (
    Website,
    KnowledgeFiles,
    TextKnowledge
)
from src.utils.logger import logger


async def _get_user_subscription_and_plan_async(
    db: AsyncSession,
    user_id: str
) -> tuple[Optional[UserSubscription], Optional[SubscriptionPlan]]:
    """
    Async version: Get user's active subscription and associated plan.

    Returns:
        Tuple of (subscription, plan) or (None, None) if no active subscription
    """
    result = await db.execute(
        select(UserSubscription).where(
            UserSubscription.user_id == user_id,
            UserSubscription.status.in_([SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL])
        )
    )
    subscription = result.scalar_one_or_none()

    if not subscription:
        return None, None

    result = await db.execute(
        select(SubscriptionPlan).where(
            SubscriptionPlan.id == subscription.plan_id
        )
    )
    plan = result.scalar_one_or_none()

    return subscription, plan


def get_user_subscription_and_plan(
    db: AsyncSession,
    user_id: str
) -> tuple[Optional[UserSubscription], Optional[SubscriptionPlan]]:
    """
    DEPRECATED: Use _get_user_subscription_and_plan_async() instead.

    This synchronous version is kept for backward compatibility but returns None.
    All middleware now uses the async version.

    Returns:
        Tuple of (None, None) - deprecated, always returns None
    """
    logger.warning(
        "get_user_subscription_and_plan() is deprecated. "
        "Use _get_user_subscription_and_plan_async() instead."
    )
    return None, None


class WorkspaceLimitChecker:
    """
    Dependency for checking workspace creation limit.

    Verifies that the user hasn't exceeded their plan's max_workspaces limit.
    """

    async def __call__(
        self,
        request: Request,
        current_user: dict = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
    ):
        """Check if user can create another workspace."""
        user_id = current_user.get("identity")

        subscription, plan = await _get_user_subscription_and_plan_async(db, user_id)

        if not subscription or not plan:
            # No subscription = default free tier (allow 1 workspace)
            result = await db.execute(
                select(func.count(Workspace.id)).where(Workspace.user_id == user_id)
            )
            current_count = result.scalar() or 0

            if current_count >= 100:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Workspace limit reached (100/100). Please subscribe to a plan to create more workspaces."
                )
            return

        # Check plan limit
        if plan.max_workspaces == -1:
            # Unlimited
            return

        result = await db.execute(
            select(func.count(Workspace.id)).where(Workspace.user_id == user_id)
        )
        current_count = result.scalar() or 0

        if current_count >= 100:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Workspace limit reached (100/100). Please subscribe to a plan to create more workspaces."
            )


class MemberLimitChecker:
    """
    Dependency for checking workspace member limit.

    Verifies that the workspace hasn't exceeded its plan's max_members_per_workspace limit.
    """

    def __init__(self, workspace_id_param: str = "workspace_id"):
        """
        Initialize member limit checker.

        Args:
            workspace_id_param: Name of the path/query parameter containing workspace_id
        """
        self.workspace_id_param = workspace_id_param

    async def __call__(
        self,
        request: Request,
        current_user: dict = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
    ):
        """Check if workspace can add another member."""
        # Extract workspace_id from path params
        workspace_id = request.path_params.get(self.workspace_id_param)
        if not workspace_id:
            # Try query params
            workspace_id = request.query_params.get(self.workspace_id_param)

        if not workspace_id:
            logger.warning(f"Member limit check: workspace_id not found in request")
            return  # Skip check if workspace_id not available

        # Get workspace
        result = await db.execute(
            select(Workspace).where(Workspace.id == workspace_id)
        )
        workspace = result.scalar_one_or_none()
        if not workspace:
            return  # Workspace doesn't exist, let the endpoint handle it

        # Get workspace creator's subscription
        subscription, plan = await _get_user_subscription_and_plan_async(db, workspace.user_id)

        # Count current active members
        result = await db.execute(
            select(func.count(WorkspaceMembers.id)).where(
                WorkspaceMembers.workspace_id == workspace_id,
                WorkspaceMembers.status == "active"
            )
        )
        current_member_count = result.scalar() or 0

        if not subscription or not plan:
            # Default free tier limit: 3 members
            if current_member_count >= 3:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Member limit reached ({current_member_count}/3). Please subscribe to a plan to add more members."
                )
            return

        # Check plan limit
        if plan.max_members_per_workspace == -1:
            # Unlimited
            return

        # Enforce plan limit
        if current_member_count >= plan.max_members_per_workspace:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Member limit reached ({current_member_count}/{plan.max_members_per_workspace}). Upgrade your plan to add more members."
            )



class KnowledgeItemLimitChecker:
    """
    Dependency for checking knowledge item creation limit.

    Verifies that the user hasn't exceeded their plan's max_knowledge_items limit.
    """

    async def __call__(
        self,
        request: Request,
        current_user: dict = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
    ):
        """Check if user can create another knowledge item."""
        user_id = current_user.get("identity")

        subscription, plan = await _get_user_subscription_and_plan_async(db, user_id)

        # Count all knowledge items across all types
        # Query count for each knowledge type that belongs to user's workspaces
        website_result = await db.execute(
            select(func.count(Website.id))
            .join(Workspace, Website.workspace_id == Workspace.id)
            .where(Workspace.user_id == user_id)
        )
        website_count = website_result.scalar() or 0

        files_result = await db.execute(
            select(func.count(KnowledgeFiles.id))
            .join(Workspace, KnowledgeFiles.workspace_id == Workspace.id)
            .where(Workspace.user_id == user_id)
        )
        files_count = files_result.scalar() or 0

        text_result = await db.execute(
            select(func.count(TextKnowledge.id))
            .join(Workspace, TextKnowledge.workspace_id == Workspace.id)
            .where(Workspace.user_id == user_id)
        )
        text_count = text_result.scalar() or 0

        # Total knowledge items across all types
        current_count = website_count + files_count + text_count

        if not subscription or not plan:
            # Default free tier (allow 100 knowledge items)
            if current_count >= 100:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Knowledge item limit reached ({current_count}/100). Please subscribe to a plan to add more items."
                )
            return

        # Check plan limit
        if plan.max_knowledge_items == -1:
            # Unlimited
            return

        # Enforce plan limit
        if current_count >= plan.max_knowledge_items:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Knowledge item limit reached ({current_count}/{plan.max_knowledge_items}). Upgrade your plan to add more items."
            )


class APICallLimiter:
    """
    Dependency for tracking and limiting API calls per month.

    Increments API call counter and checks against plan's max_api_calls_per_month limit.
    """

    def __init__(self, increment: bool = True):
        """
        Initialize API call limiter.

        Args:
            increment: Whether to increment the counter (False for read-only checks)
        """
        self.increment = increment

    async def __call__(
        self,
        request: Request,
        current_user: dict = Depends(get_current_user),
        db: AsyncSession = Depends(get_db)
    ):
        """Track and check API call limit."""
        user_id = current_user.get("identity")

        subscription, plan = await _get_user_subscription_and_plan_async(db, user_id)

        if not subscription or not plan:
            # No subscription = default free tier (1000 calls/month)
            # TODO: Implement tracking for users without subscription
            return

        # Check if usage period needs reset
        if subscription.usage_reset_date and subscription.usage_reset_date < datetime.utcnow():
            subscription.current_api_calls = 0
            subscription.usage_reset_date = datetime.utcnow() + timedelta(days=30)
            await db.commit()

        # Check limit (before incrementing)
        if plan.max_api_calls_per_month != -1:  # -1 = unlimited
            if subscription.current_api_calls >= plan.max_api_calls_per_month:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"API call limit reached ({subscription.current_api_calls}/{plan.max_api_calls_per_month}). Upgrade your plan or wait until {subscription.usage_reset_date.strftime('%Y-%m-%d')}."
                )

        # Increment counter
        if self.increment:
            subscription.current_api_calls += 1
            await db.commit()


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def increment_api_calls(db: AsyncSession, user_id: str) -> None:
    """
    Manually increment API call counter for a user.

    NOTE: Temporarily disabled - subscription tracking disabled.

    Args:
        db: Database session
        user_id: User UUID
    """
    # Temporarily disabled - subscription tracking not active
    logger.debug(f"API call tracking disabled for user {user_id}")
    return


def reset_monthly_usage(db: AsyncSession) -> int:
    """
    Reset monthly usage for all subscriptions (called by cron job).

    NOTE: Temporarily disabled - subscription tracking disabled.

    Returns:
        Number of subscriptions reset
    """
    # Temporarily disabled - subscription tracking not active
    logger.info("Monthly usage reset disabled - subscription tracking not active")
    return 0


# ============================================================================
# DEPENDENCY FACTORIES (for easier usage in routes)
# ============================================================================

def check_workspace_limit():
    """Factory function to create workspace limit checker dependency."""
    return WorkspaceLimitChecker()


def check_member_limit(workspace_id_param: str = "workspace_id"):
    """Factory function to create member limit checker dependency."""
    return MemberLimitChecker(workspace_id_param)


def check_knowledge_item_limit():
    """Factory function to create knowledge item limit checker dependency."""
    return KnowledgeItemLimitChecker()


def check_api_limit(increment: bool = True):
    """Factory function to create API call limiter dependency."""
    return APICallLimiter(increment)
