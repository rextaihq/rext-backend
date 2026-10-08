"""
Usage limit checking middleware for subscription plans.

This module provides dependency injection utilities for checking user's
resource usage against their subscription plan limits before allowing
resource-intensive operations.

Usage:
    from src.api.middleware.usage_limiter import check_workspace_limit

    @router.post("/workspaces")
    def create_workspace(
        _: None = Depends(check_workspace_limit()),
        db: AsyncSession = Depends(get_db),
        current_user: dict = Depends(get_current_user)
    ):
        # Create workspace...
"""

import warnings
from typing import Optional
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.config import get_settings
from src.api.database.async_database import get_async_db as get_db
from src.api.models.subscription_models.plans import SubscriptionPlan
from src.api.models.subscription_models.subscriptions import (
    SubscriptionStatus,
    UserSubscription,
    subscription_grants_access,
)
from src.api.models.workspace_models.workspace_member import WorkspaceMembers
from src.api.models.workspace_models.workspace_model import WorkspaceModel as Workspace
from src.api.security.dependencies import get_current_user
from src.services.credit_grants import grant_balance
from src.utils import rbac_utils
from src.utils.logger import logger


async def _get_user_subscription_and_plan_async(
    db: AsyncSession, user_id: str
) -> tuple[Optional[UserSubscription], Optional[SubscriptionPlan]]:
    """
    Async version: Get user's active subscription and associated plan.

    Returns:
        Tuple of (subscription, plan) or (None, None) if no active subscription
    """
    from sqlalchemy import case

    priority = case((UserSubscription.status == SubscriptionStatus.ACTIVE, 1), else_=0)
    result = await db.execute(
        select(UserSubscription)
        .where(UserSubscription.user_id == user_id, subscription_grants_access())
        .order_by(priority.desc(), UserSubscription.created_at.desc())
        .limit(1)
    )
    subscription = result.scalar_one_or_none()

    if not subscription:
        return None, None

    result = await db.execute(
        select(SubscriptionPlan).where(SubscriptionPlan.id == subscription.plan_id)
    )
    plan = result.scalar_one_or_none()

    return subscription, plan


async def get_user_subscription_and_plan_async(
    db: AsyncSession,
    user_id: str,
) -> tuple[Optional[UserSubscription], Optional[SubscriptionPlan]]:
    """Public async helper for subscription+plan retrieval."""
    return await _get_user_subscription_and_plan_async(db, user_id)


def get_user_subscription_and_plan(
    db: AsyncSession,
    user_id: str,
) -> tuple[Optional[UserSubscription], Optional[SubscriptionPlan]]:
    """
    DEPRECATED: synchronous helper removed.

    Use `await get_user_subscription_and_plan_async(db, user_id)` instead.
    """
    warnings.warn(
        "get_user_subscription_and_plan() is deprecated and no longer supported. "
        "Use await get_user_subscription_and_plan_async(db, user_id).",
        DeprecationWarning,
        stacklevel=2,
    )
    raise RuntimeError("Deprecated sync helper called: use get_user_subscription_and_plan_async()")


async def _live_workspace_count(db: AsyncSession, user_id) -> int:
    """The workspaces the user owns that aren't in the trash."""
    result = await db.execute(
        select(func.count(Workspace.id)).where(
            Workspace.user_id == user_id, Workspace.deleted_at.is_(None)
        )
    )
    return result.scalar() or 0


class WorkspaceLimitChecker:
    """
    Dependency for checking workspace creation limit.

    The one gate on a new (or restored) workspace: the user's live workspaces against
    their plan's max_workspaces. A super admin isn't limited, nor is a plan without a
    limit (-1, or none set); no subscription means the free tier's one workspace.
    """

    async def __call__(
        self,
        request: Request,
        current_user: dict = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ):
        """Check if user can create another workspace."""
        user_id = current_user.get("identity")
        settings = get_settings()
        if settings.ENVIRONMENT.lower() == "local" and settings.LOCAL_UNLIMITED_WORKSPACES:
            logger.warning("Local unlimited workspace override enabled")
            return

        if await rbac_utils.is_user_super_admin(db, UUID(str(user_id))):
            return

        subscription, plan = await _get_user_subscription_and_plan_async(db, user_id)

        if not subscription or not plan:
            # No subscription = default free tier (allow 1 workspace)
            if await _live_workspace_count(db, user_id) >= 1:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Workspace limit reached (1/1). Please subscribe to a plan to create more workspaces.",
                )
            return

        # Check plan limit
        if plan.max_workspaces is None or plan.max_workspaces == -1:
            # Unlimited
            return

        current_count = await _live_workspace_count(db, user_id)

        if current_count >= plan.max_workspaces:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Workspace limit reached ({current_count}/{plan.max_workspaces}). Please upgrade your plan to create more workspaces.",
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
        db: AsyncSession = Depends(get_db),
    ):
        """Check if workspace can add another member."""
        # Extract workspace_id from path params
        workspace_id = request.path_params.get(self.workspace_id_param)
        if not workspace_id:
            # Try query params
            workspace_id = request.query_params.get(self.workspace_id_param)

        if not workspace_id:
            logger.warning("Member limit check: workspace_id not found in request")
            return  # Skip check if workspace_id not available

        # Get workspace
        result = await db.execute(select(Workspace).where(Workspace.id == workspace_id))
        workspace = result.scalar_one_or_none()
        if not workspace:
            return  # Workspace doesn't exist, let the endpoint handle it

        # Get workspace creator's subscription
        subscription, plan = await _get_user_subscription_and_plan_async(db, workspace.user_id)

        # Count current active members
        result = await db.execute(
            select(func.count(WorkspaceMembers.id)).where(
                WorkspaceMembers.workspace_id == workspace_id, WorkspaceMembers.status == "active"
            )
        )
        current_member_count = result.scalar() or 0

        if not subscription or not plan:
            # Default free tier limit: 3 members
            if current_member_count >= 3:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Member limit reached ({current_member_count}/3). Please subscribe to a plan to add more members.",
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
                detail=f"Member limit reached ({current_member_count}/{plan.max_members_per_workspace}). Upgrade your plan to add more members.",
            )


class CreditLimiter:
    """
    Dependency for pre-flight credit checks at route level.

    Use at the route that kicks off generation to verify the user has
    enough credits BEFORE the expensive pipeline starts.
    Does not deduct — deduction happens per-stage inside the flow nodes.
    """

    def __init__(self, required: int = 15):
        self.required = required

    async def __call__(
        self,
        request: Request,
        current_user: dict = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ):
        user_id = current_user.get("identity")
        settings = get_settings()
        if settings.ENVIRONMENT.lower() == "local" and settings.LOCAL_UNLIMITED_WORKSPACES:
            logger.warning("Local unlimited workspace override enabled")
            return
        subscription, plan = await _get_user_subscription_and_plan_async(db, user_id)

        if not subscription or not plan:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail="No active subscription. Start a trial to generate articles.",
            )

        if plan.credits_per_month is None:
            return  # Enterprise: unlimited

        # The monthly credits plus any unexpired grant (an offer's bonus).
        available = (subscription.current_credits or 0) + await grant_balance(db, subscription.id)
        if available < self.required:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    f"Insufficient credits: {available} available, "
                    f"{self.required} required. Upgrade your plan or wait for your monthly reset."
                ),
            )


def check_credit_limit(required: int = 15):
    """Factory for CreditLimiter dependency."""
    return CreditLimiter(required)


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================


# ============================================================================
# DEPENDENCY FACTORIES (for easier usage in routes)
# ============================================================================


def check_workspace_limit():
    """Factory function to create workspace limit checker dependency."""
    return WorkspaceLimitChecker()


def check_member_limit(workspace_id_param: str = "workspace_id"):
    """Factory function to create member limit checker dependency."""
    return MemberLimitChecker(workspace_id_param)
