"""
Workspace Stats Routes - Onboarding & Dashboard Statistics

Provides real-time statistics for workspace onboarding tracking and dashboard.
"""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from src.api.database.async_database import get_async_db
from src.api.security.dependencies import get_current_user
from src.services.workspace_service import WorkspaceService
from src.services.subscription_service import SubscriptionService
from src.utils.auth_utils import verify_current_user
from src.utils.route_decorators import db_transaction_handler, require_permissions

router = APIRouter()


@router.get("/{workspace_id}/stats")
@require_permissions("workspace.read", workspace_scoped=True)
@db_transaction_handler("get workspace stats", auto_commit=False)
async def get_workspace_stats(
    workspace_id: str,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user)
):
    """
    Get workspace statistics for onboarding tracking and dashboard.

    Returns real-time counts for:
    - Content items
    - Knowledge base items
    - Team members
    - Feature availability (content builder)

    Args:
        workspace_id: Workspace UUID (path parameter)

    Returns:
        Statistics object with all counts
    """
    user_id = user.get("identity")
    await verify_current_user(db, user_id)

    workspace_uuid = UUID(workspace_id)

    # Delegate analytics to the service layer (single source of truth)
    workspace_service = WorkspaceService(db)
    analytics = await workspace_service.get_workspace_analytics(workspace_uuid)

    # Check feature availability from user's subscription
    subscription_service = SubscriptionService(db)
    user_subscription = await subscription_service.get_subscription_by_user(UUID(user_id))

    # Default to True if no subscription (free tier) or if plan doesn't specify
    has_content_builder = True

    if user_subscription and user_subscription.plan:
        plan_features = user_subscription.plan.features or {}

        # Check if features are explicitly set to False (disabled)
        # If not set, default to True (enabled)
        if 'content_builder' in plan_features:
            has_content_builder = bool(plan_features.get('content_builder'))

    stats = {
        "workspace_exists": True,
        "content_count": analytics["content_count"],
        "knowledge_items_count": analytics["knowledge_stats"]["total"],
        "members_count": analytics["members_count"],
        "has_content_builder": has_content_builder,
    }

    return stats