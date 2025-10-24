"""
Workspace Stats Routes - Onboarding & Dashboard Statistics

Provides real-time statistics for workspace onboarding tracking and dashboard.
"""

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from src.api.database.async_database import get_async_db
from src.api.security.dependencies import get_current_user
from src.api.models.topic_models.topic_models import TopicsModel
from src.api.models.content_models.content import Content
from src.api.models.knowledge_models.knowledge_model import Website, KnowledgeFiles, TextKnowledge
from src.api.models.workspace_models.workspace_member import WorkspaceMembers
from src.services.subscription_service import SubscriptionService
from src.utils.response_utils import success
from src.utils.route_decorators import db_transaction_handler, require_permissions
from src.utils.auth_utils import verify_current_user

router = APIRouter()


@router.get("/{workspace_id}/stats")
@require_permissions(["workspace.read"], workspace_scoped=True)
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
    - Topics
    - Content items
    - Knowledge base items
    - Team members
    - Feature availability (topic/content builders)

    Args:
        workspace_id: Workspace UUID (path parameter)

    Returns:
        Statistics object with all counts
    """
    user_id = user.get("identity")
    await verify_current_user(db, user_id)

    workspace_uuid = UUID(workspace_id)

    # Count topics
    result = await db.execute(
        select(func.count(TopicsModel.id)).where(
            TopicsModel.workspace_id == workspace_uuid
        )
    )
    topics_count = result.scalar() or 0

    # Count content items (non-deleted)
    result = await db.execute(
        select(func.count(Content.id)).where(
            Content.workspace_id == workspace_uuid,
            Content.deleted_at == None
        )
    )
    content_count = result.scalar() or 0

    # Count knowledge items (all types combined)
    result = await db.execute(
        select(func.count(Website.id)).where(
            Website.workspace_id == workspace_uuid
        )
    )
    web_knowledge_count = result.scalar() or 0

    result = await db.execute(
        select(func.count(KnowledgeFiles.id)).where(
            KnowledgeFiles.workspace_id == workspace_uuid
        )
    )
    files_count = result.scalar() or 0

    result = await db.execute(
        select(func.count(TextKnowledge.id)).where(
            TextKnowledge.workspace_id == workspace_uuid
        )
    )
    text_knowledge_count = result.scalar() or 0

    knowledge_items_count = web_knowledge_count + files_count + text_knowledge_count

    # Count workspace members
    result = await db.execute(
        select(func.count(WorkspaceMembers.id)).where(
            WorkspaceMembers.workspace_id == workspace_uuid
        )
    )
    members_count = result.scalar() or 0

    # Check feature availability from user's subscription
    subscription_service = SubscriptionService(db)
    user_subscription = await subscription_service.get_subscription_by_user(UUID(user_id))

    # Default to True if no subscription (free tier) or if plan doesn't specify
    has_topic_builder = True
    has_content_builder = True

    if user_subscription and user_subscription.plan:
        plan_features = user_subscription.plan.features or {}

        # Check if features are explicitly set to False (disabled)
        # If not set, default to True (enabled)
        if 'topic_builder' in plan_features:
            has_topic_builder = bool(plan_features.get('topic_builder'))

        if 'content_builder' in plan_features:
            has_content_builder = bool(plan_features.get('content_builder'))

    stats = {
        "workspace_exists": True,  # If we got here, workspace exists
        "topics_count": topics_count,
        "content_count": content_count,
        "knowledge_items_count": knowledge_items_count,
        "members_count": members_count,
        "has_topic_builder": has_topic_builder,
        "has_content_builder": has_content_builder,
    }

    return stats
