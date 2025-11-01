from fastapi import APIRouter, Depends, Request, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from src.utils.logger import logger
from src.utils.route_decorators import db_transaction_handler, require_permissions
from src.api.database.async_database import get_async_db
from src.api.security.dependencies import get_current_user
from src.api.middleware.exceptions import WrextValidationException
from src.api.schema.content_schema import ContentCreate, ContentUpdate
from src.utils.workspace_utils import resolve_and_verify_workspace
from src.services.content_service import ContentService
from src.services.content_progress_service import ContentProgressService
from src.api.tasks.content_generation import run_content_generation_background


router = APIRouter()


# -------------------------
# Create New Content
# -------------------------
@router.post("/")
@db_transaction_handler("create content", "Content created successfully - generation started in background")
@require_permissions("content.create", workspace_scoped=True)
async def create_content(
    data: ContentCreate,
    request: Request,
    workspace_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user)
):
    """
    Create new content in a workspace and start generation in background.

    This endpoint:
    1. Creates content record with status="generating"
    2. Initializes progress tracking
    3. Returns immediately with content details
    4. Triggers background task for content generation
    5. Frontend can subscribe to SSE for real-time progress updates

    Args:
        workspace_id: Workspace UUID or slug (query parameter)
        data: Content creation data
        background_tasks: FastAPI background tasks

    Returns:
        Content data with id (use as operation_id for SSE subscription)

    Requires:
        - JWT authentication
        - Workspace membership verification
    """
    user_id = user.get("identity")

    # Verify workspace access and membership in one call
    workspace, membership = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))

    # If workspace_id in body is provided, verify it matches
    if data.workspace_id:
        if data.workspace_id != workspace.id:
            raise WrextValidationException(
                message="Workspace ID mismatch",
                context={"path_workspace_id": str(workspace_id), "body_workspace_id": str(data.workspace_id)}
            )

    # Use ContentService to create content record
    service = ContentService(db)
    content = await service.create_content(
        workspace_id=workspace.id,
        user_id=UUID(user_id),
        data=data
    )

    # Initialize progress tracking
    # progress_service = ContentProgressService(db)
    # await progress_service.initialize_progress(
    #     content_id=content.id,
    #     step="initializing"
    # )

    # Trigger background content generation
    # Frontend should subscribe to SSE using content.id as operation_id
    # FastAPI BackgroundTasks supports async functions natively
    # background_tasks.add_task(
    #     run_content_generation_background,
    #     content_id=content.id,
    #     workspace_id=workspace.id,
    #     topic_id=data.topic_id
    # )

    logger.info(
        f"Content generation queued for content {content.id}",
        extra={"workspace_id": str(workspace.id), "topic_id": str(data.topic_id)}
    )

    content_data = content.to_dict(include_relationships=["content_metadata", "seo_data"])

    # Return content data immediately - generation runs in background
    # Frontend can use content.id to subscribe to progress via SSE
    return {
        "content": content_data,
        "operation_id": str(content.id),  # For SSE subscription
        "message": "Content generation started in background"
    }


# -------------------------
# Update Content
# -------------------------
@router.put("/{content_id}")
@db_transaction_handler("update content", "Content updated successfully")
@require_permissions("content.update", workspace_scoped=True)
async def update_content(
    content_id: UUID,
    data: ContentUpdate,
    request: Request,
    workspace_id: str,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user)
):
    """Update existing content"""
    user_id = user.get("identity")

    # Verify workspace access and membership in one call
    workspace, membership = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))

    # Check if user is trying to publish content
    if data.status == "published":
        from src.utils.rbac_utils import require_permission
        await require_permission(
            db=db,
            user_id=UUID(user_id),
            permission_name="content.publish",
            workspace_id=workspace.id,
            resource_name="content"
        )

    # Use ContentService to update content
    service = ContentService(db)
    content = await service.update_content(
        content_id=content_id,
        workspace_id=workspace.id,
        user_id=UUID(user_id),
        data=data
    )

    content_data = content.to_dict(include_relationships=["content_metadata", "seo_data"])

    # Return raw data - decorator handles success response and commit
    return {"content": content_data}


# -------------------------
# Delete Content (Soft Delete)
# -------------------------
@router.delete("/{content_id}")
@db_transaction_handler("delete content", "Content deleted successfully")
@require_permissions("content.delete", workspace_scoped=True)
async def delete_content(
    content_id: UUID,
    request: Request,
    workspace_id: str,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user)
):
    """Soft delete content by setting deleted_at timestamp"""
    user_id = user.get("identity")
    print("Deleting content:", content_id)

    # Verify workspace access and membership in one call
    workspace, membership = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))
    print("Workspace verified:", workspace.id)
    # Use ContentService to delete content
    service = ContentService(db)
    await service.delete_content(
        content_id=content_id,
        workspace_id=workspace.id
    )

    # Return raw data - decorator handles success response and commit
    return {"content_id": str(content_id)}


# -------------------------
# Get Content Generation Progress
# -------------------------
@router.get("/{content_id}/progress")
@require_permissions("content.read", workspace_scoped=True)
async def get_content_progress(
    content_id: UUID,
    workspace_id: str,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user)
):
    """
    Get current generation progress for a content item.

    This endpoint allows fetching progress state without SSE,
    useful for:
    - Page refreshes during generation
    - Initial state before SSE connection
    - Polling fallback if SSE unavailable

    Returns:
        Progress data with current step, percentage, and message
    """
    user_id = user.get("identity")

    # Verify workspace access
    workspace, membership = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))

    # Get progress
    progress_service = ContentProgressService(db)
    progress = await progress_service.get_progress(content_id)

    if not progress:
        return {
            "content_id": str(content_id),
            "current_step": None,
            "progress_percent": 0,
            "status_message": "Progress data not found",
            "step_details": None,
            "estimated_time_remaining": None,
            "updated_at": None
        }

    return progress


# -------------------------
# Retry Content Generation
# -------------------------
@router.post("/{content_id}/retry")
@db_transaction_handler("retry content generation", "Content generation retry initiated")
@require_permissions("content.update", workspace_scoped=True)
async def retry_content_generation(
    content_id: UUID,
    workspace_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user)
):
    """
    Retry content generation for a failed or existing content item.

    This endpoint:
    1. Resets the content status to "generating"
    2. Clears any existing progress data
    3. Triggers the background generation task

    Useful for:
    - Retrying after generation failures
    - Regenerating content with same parameters

    Returns:
        Success message with content_id
    """
    user_id = user.get("identity")

    # Verify workspace access
    workspace, membership = await resolve_and_verify_workspace(db, workspace_id, UUID(user_id))

    # Initialize services
    service = ContentService(db)
    progress_service = ContentProgressService(db)

    # Get the content item
    content = await service.get_content_by_id(content_id, workspace.id)
    if not content:
        raise WrextValidationException(
            message="Content not found",
            context={"content_id": str(content_id)}
        )

    # Reset status to generating
    content.status = "generating"
    db.add(content)

    # Clear existing progress data
    await progress_service.reset_progress(content_id)

    logger.info(f"Retrying content generation for content {content_id}")

    # Trigger background generation
    background_tasks.add_task(
        run_content_generation_background,
        content_id=content_id,
        workspace_id=workspace.id,
        topic_id=content.topic_id
    )

    return {"content_id": str(content_id), "status": "generating"}
