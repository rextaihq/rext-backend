from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from src.utils.logger import logger
from src.utils.response_utils import success, error
from src.utils.route_decorators import db_transaction_handler
from src.utils.auth_utils import verify_current_user
from src.api.database.async_database import get_async_db
from src.api.security.dependencies import get_current_user
from src.api.middleware.exceptions import (
    ResourceNotFoundException,
)
from src.services.workspace_service import WorkspaceService

router = APIRouter()


# -------------------------
# Health Check
# -------------------------
@router.get("/")
async def get_status(request: Request):
    logger.info("Workspace Route health check called.")
    return success(
        data={"status": "operational", "service": "workspace_service"},
        request=request,
        message="Workspace service is working!"
    )


# -------------------------
# Get all workspaces for user
# -------------------------
@router.get("/all")
@db_transaction_handler("get workspaces", auto_commit=False)
async def get_workspaces(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user)):
    user_id = user.get("identity")
    db_user = await verify_current_user(db, user_id)

    # Use workspace service
    workspace_service = WorkspaceService(db)
    workspace_data = await workspace_service.get_user_workspaces(UUID(user_id))

    # Return raw data - decorator handles success response
    return {"workspaces": workspace_data, "total_count": len(workspace_data)}

# -------------------------
# Get workspace by ID
# -------------------------
@router.get("/detail")
@db_transaction_handler("get workspace by id", auto_commit=False)
async def get_workspace_by_id(
    workspace_id: str,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user)
):
    """
    Get workspace by ID using query parameter.
    
    Args:
        workspace_id: Workspace UUID (query parameter)
    """
    user_id = user.get("identity")
    db_user = await verify_current_user(db, user_id)

    # Use workspace service
    workspace_service = WorkspaceService(db)

    # Get workspace with brand voice
    workspace_data = await workspace_service.get_workspace_with_brand_voice(UUID(workspace_id))

    # Get analytics with word counts
    analytics = await workspace_service.get_workspace_analytics(UUID(workspace_id), include_word_counts=True)

    # Merge analytics into workspace data
    workspace_data["knowledge_stats"] = analytics["knowledge_stats"]
    workspace_data["analytics"] = {
        "knowledge_counts": {
            "web_knowledge": analytics["knowledge_stats"]["web_knowledge"],
            "files": analytics["knowledge_stats"]["files"],
            "text_knowledge": analytics["knowledge_stats"]["text_knowledge"],
            "total_knowledge_items": analytics["knowledge_stats"]["total"]
        },
        "content_metrics": analytics.get("content_metrics", {}),
        "team_metrics": {
            "total_members": analytics["members_count"]
        }
    }

    # Return raw data - decorator handles success response
    return {"workspace": workspace_data}


# -------------------------
# Get workspace by slug
# -------------------------
@router.get("/slug/{workspace_slug}")
@db_transaction_handler("get workspace by slug", auto_commit=False)
async def get_workspace_by_slug(
    workspace_slug: str,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user)
):
    """
    Get workspace by slug instead of ID.
    This is the preferred endpoint for frontend routing.
    """
    user_id = user.get("identity")
    db_user = await verify_current_user(db, user_id)

    # First, find workspace by slug (need to add this method to service or handle here)
    from sqlalchemy import select
    from src.api.models.workspace_models.workspace_model import WorkspaceModel
    from src.api.models.workspace_models.workspace_member import WorkspaceMembers

    workspace_query = (
        select(WorkspaceModel)
        .join(WorkspaceMembers, WorkspaceMembers.workspace_id == WorkspaceModel.id)
        .where(WorkspaceModel.slug == workspace_slug, WorkspaceMembers.user_id == user_id)
    )
    result = await db.execute(workspace_query)
    workspace = result.scalar_one_or_none()

    if not workspace:
        raise ResourceNotFoundException(resource_type="workspace", resource_id=workspace_slug)

    # Use workspace service for the rest
    workspace_service = WorkspaceService(db)
    workspace_data = await workspace_service.get_workspace_with_brand_voice(workspace.id)

    # Get analytics with word counts
    analytics = await workspace_service.get_workspace_analytics(workspace.id, include_word_counts=True)

    # Merge analytics into workspace data
    workspace_data["knowledge_stats"] = analytics["knowledge_stats"]
    workspace_data["analytics"] = {
        "knowledge_counts": {
            "web_knowledge": analytics["knowledge_stats"]["web_knowledge"],
            "files": analytics["knowledge_stats"]["files"],
            "text_knowledge": analytics["knowledge_stats"]["text_knowledge"],
            "total_knowledge_items": analytics["knowledge_stats"]["total"]
        },
        "content_metrics": analytics.get("content_metrics", {}),
        "team_metrics": {
            "total_members": analytics["members_count"]
        }
    }

    # Return raw data - decorator handles success response
    return {"workspace": workspace_data}
