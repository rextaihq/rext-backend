from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from src.utils.logger import logger
from src.utils.response_utils import success, error
from src.utils.route_decorators import db_transaction_handler, require_permissions
from src.utils.auth_utils import verify_current_user
from src.api.database.async_database import get_async_db
from src.api.security.dependencies import get_current_user
from src.api.middleware.exceptions import (
    ResourceNotFoundException,
)
from src.services.workspace_service import WorkspaceService

router = APIRouter()

def _merge_analytics_into_workspace(workspace_data: dict, analytics: dict) -> dict:
    """
    Merge analytics data into workspace response dict.

    Transforms the flat analytics dict from WorkspaceService.get_workspace_analytics()
    into the nested structure expected by the frontend.

    Args:
        workspace_data: Workspace dict from get_workspace_with_brand_voice()
        analytics: Analytics dict from get_workspace_analytics()

    Returns:
        The workspace_data dict with analytics merged in.
    """
    workspace_data["knowledge_stats"] = analytics["knowledge_stats"]
    workspace_data["analytics"] = {
        "knowledge_counts": {
            "web_knowledge": analytics["knowledge_stats"]["web_knowledge"],
            "files": analytics["knowledge_stats"]["files"],
            "text_knowledge": analytics["knowledge_stats"]["text_knowledge"],
            "total_knowledge_items": analytics["knowledge_stats"]["total"],
        },
        "content_metrics": analytics.get("content_metrics", {}),
        "team_metrics": {
            "total_members": analytics["members_count"],
        },
    }
    return workspace_data

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
@require_permissions("workspace.read", workspace_scoped=False)
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
@require_permissions("workspace.read")
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

    _merge_analytics_into_workspace(workspace_data, analytics)

    # Return raw data - decorator handles success response
    return {"workspace": workspace_data}


# -------------------------
# Get workspace by slug
# -------------------------
@router.get("/slug/{workspace_slug}")
@require_permissions("workspace.read", workspace_scoped=False)
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

    # Use workspace service
    workspace_service = WorkspaceService(db)
    workspace = await workspace_service.get_workspace_by_slug_for_user(workspace_slug, UUID(user_id))
    workspace_data = await workspace_service.get_workspace_with_brand_voice(workspace.id)

    # Get analytics with word counts
    analytics = await workspace_service.get_workspace_analytics(workspace.id, include_word_counts=True)

    # Merge analytics into workspace data
    _merge_analytics_into_workspace(workspace_data, analytics)

    # Return raw data - decorator handles success response
    return {"workspace": workspace_data}


# -------------------------
# Get workspace by ID (RESTful endpoint)
# -------------------------
@router.get("/{workspace_id}")
@require_permissions("workspace.read")
@db_transaction_handler("get workspace by id (path)", auto_commit=False)
async def get_workspace_by_id_path(
    workspace_id: str,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user)
):
    """
    Get workspace by ID using path parameter.
    RESTful endpoint for frontend compatibility.

    This endpoint handles both UUID and slug formats:
    - If workspace_id is a UUID: fetch directly by ID
    - If workspace_id is a slug: fetch by slug

    Args:
        workspace_id: Workspace UUID or slug (path parameter)
    """
    user_id = user.get("identity")
    db_user = await verify_current_user(db, user_id)

    # Use workspace service
    workspace_service = WorkspaceService(db)
    workspace = await workspace_service.get_workspace_by_id_or_slug_for_user(workspace_id, UUID(user_id))
    workspace_data = await workspace_service.get_workspace_with_brand_voice(workspace.id)

    # Get analytics with word counts
    analytics = await workspace_service.get_workspace_analytics(workspace.id, include_word_counts=True)

    # Merge analytics into workspace data
    _merge_analytics_into_workspace(workspace_data, analytics)

    # Return raw data - decorator handles success response
    return {"workspace": workspace_data}


# -------------------------
# Update workspace
# -------------------------
@router.put("/{workspace_id}")
@require_permissions("workspace.update", workspace_scoped=True)
@db_transaction_handler("update workspace", auto_commit=True)
async def update_workspace(
    workspace_id: str,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user)
):
    """
    Update workspace details (name, slug, description, url).

    Args:
        workspace_id: Workspace UUID or slug

    Body:
        {
          "title": "New Name",
          "slug": "new-slug",
          "description": "New description",
          "url": "https://example.com"
        }
    """
    user_id = user.get("identity")
    db_user = await verify_current_user(db, user_id)

    # Parse request body
    body = await request.json()

    # Use workspace service
    workspace_service = WorkspaceService(db)

    # Get workspace first to verify access
    from src.utils.workspace_utils import resolve_and_verify_workspace
    workspace, _ = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))

    # Update workspace
    updated_workspace = await workspace_service.update_workspace(
        workspace.id,
        title=body.get("title"),
        slug=body.get("slug"),
        description=body.get("description"),
        url=body.get("url")
    )

    logger.info(
        f"Workspace updated: {workspace.id}",
        extra={"workspace_id": str(workspace.id), "user_id": user_id}
    )

    # Return raw data - decorator handles success response
    return {"workspace": updated_workspace}


# -------------------------
# Delete workspace
# -------------------------
@router.delete("/{workspace_id}")
@require_permissions("workspace.delete", workspace_scoped=True)
@db_transaction_handler("delete workspace", auto_commit=True)
async def delete_workspace_endpoint(
    workspace_id: str,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user)
):
    """
    Delete workspace permanently.

    Only workspace owners can delete workspaces.
    All related data (knowledge, topics, content) will be cascade deleted.

    Args:
        workspace_id: Workspace UUID or slug
    """
    user_id = user.get("identity")
    db_user = await verify_current_user(db, user_id)

    # Use workspace service
    workspace_service = WorkspaceService(db)

    # Get workspace and verify user is owner
    workspace = await workspace_service.get_workspace_by_id_or_slug_for_user(workspace_id, UUID(user_id))

    # Verify user is workspace owner (raises ForbiddenException if not)
    await workspace_service.verify_user_is_workspace_owner(workspace.id, UUID(user_id))

    # Check remaining workspaces count
    remaining_count = await workspace_service.count_user_workspaces(UUID(user_id))
    # Subtract 1 because we're about to delete this one
    remaining_after_delete = remaining_count - 1

    # Soft delete workspace (30-day recovery period)
    await workspace_service.delete_workspace(workspace.id, UUID(user_id))

    logger.info(
        f"Workspace soft deleted: {workspace.id}",
        extra={"workspace_id": str(workspace.id), "user_id": user_id}
    )

    # Send confirmation email
    try:
        from src.services.email_service import EmailService
        from datetime import datetime, timedelta

        email_service = EmailService(db)
        recovery_date = (datetime.utcnow() + timedelta(days=30)).strftime("%B %d, %Y")

        await email_service.send_email(
            to_email=db_user.email,
            subject=f"Workspace '{workspace.name}' has been deleted",
            template_type="workspace_deleted",
            template_data={
                "user_name": db_user.display_name or db_user.email,
                "workspace_name": workspace.name,
                "recovery_period_days": 30,
                "recovery_deadline": recovery_date,
                "remaining_workspaces": remaining_after_delete,
                "is_last_workspace": remaining_after_delete == 0
            }
        )
        logger.info(f"Deletion confirmation email sent to {db_user.email}")
    except Exception as e:
        # Don't fail the deletion if email fails
        logger.error(f"Failed to send deletion confirmation email: {str(e)}")

    # Return success message with workspace count
    return {
        "message": "Workspace deleted successfully. You have 30 days to recover it if needed.",
        "recovery_period_days": 30,
        "remaining_workspaces": remaining_after_delete,
        "is_last_workspace": remaining_after_delete == 0
    }
