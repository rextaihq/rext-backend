"""
Workspace Stats Routes - Onboarding & Dashboard Statistics

Provides real-time statistics for workspace onboarding tracking and dashboard.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.database.async_database import get_async_db
from src.api.schema.response.workspace_responses import WorkspaceStatsResponse
from src.api.schema.response_schemas import SuccessResponse
from src.api.security.dependencies import get_current_user
from src.services.workspace_service import WorkspaceService
from src.utils.auth_utils import verify_current_user
from src.utils.response_utils import success
from src.utils.route_decorators import db_transaction_handler, require_permissions

router = APIRouter()


@router.get("/{workspace_id}/stats", response_model=SuccessResponse[WorkspaceStatsResponse])
@require_permissions("workspace.read", workspace_scoped=True)
@db_transaction_handler(
    "get workspace stats",
    success_message="Workspace statistics retrieved successfully",
    auto_commit=False,
)
async def get_workspace_stats(
    workspace_id: str,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user),
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

    workspace_service = WorkspaceService(db)
    analytics = await workspace_service.get_workspace_analytics(workspace_uuid)

    content_count = analytics["content_count"]
    knowledge_items_count = analytics["knowledge_stats"]["total_count"]
    members_count = analytics["members_count"]

    stats = {
        "workspace_exists": True,  # If we got here, workspace exists
        "content_count": content_count,
        "knowledge_items_count": knowledge_items_count,
        "members_count": members_count,
        "topics_count": analytics.get("topics_count", 0),
    }

    return success(data=stats, message="Workspace statistics retrieved successfully")
