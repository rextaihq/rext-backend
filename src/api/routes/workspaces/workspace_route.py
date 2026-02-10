from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.database.async_database import get_async_db
from src.api.middleware.exceptions import RextValidationException
from src.api.middleware.usage_limiter import check_workspace_limit
from src.api.schema.workspace_schema import WorkspaceSchema
from src.api.security.dependencies import get_current_user
from src.services.workspace_service import WorkspaceService
from src.utils.logger import logger
from src.utils.response_utils import created, success
from src.utils.route_decorators import db_transaction_handler, require_permissions
from langsmith import traceable, trace

router = APIRouter(
    prefix="/workspace",
    tags=["workspace"],
    responses={404: {"description": "Not found"}},
)


@router.get("/")
def get_status(request: Request):
    """Simple health check for the workspace routes."""
    logger.info("Workspace Route health check called.")
    return success(
        data={"status": "operational", "service": "workspace_service"},
        request=request,
        message="Workspace service is working!",
    )


@router.get("/all")
@require_permissions("workspace.read")
@db_transaction_handler("list workspaces", auto_commit=False)
async def get_workspaces(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
):
    """Return all workspaces available to the current user."""
    user_id = UUID(str(current_user.get("identity")))
    service = WorkspaceService(db)
    payload = await service.list_workspaces_for_user(user_id)

    return success(
        data=payload,
        request=request,
        message=f"Retrieved {payload['total_count']} workspaces successfully",
    )


@router.get("/detail")
@require_permissions("workspace.read")
@db_transaction_handler("get workspace", auto_commit=False)
async def get_workspace_by_id(
    workspace_id: str,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Return a specific workspace with brand voice data for the current user.
    
    Args:
        workspace_id: Workspace UUID (query parameter)
    """
    user_id = UUID(str(current_user.get("identity")))
    workspace_uuid = UUID(workspace_id)

    service = WorkspaceService(db)
    workspace = await service.get_workspace_for_user(workspace_uuid, user_id)

    return success(
        data={"workspace": workspace},
        request=request,
        message="Workspace retrieved successfully",
    )


@router.post("/create")
@require_permissions("workspace.create")
@db_transaction_handler("create workspace", auto_commit=True)
@traceable(
    name="Create Workspace",
    metadata={"description": "Creates a new workspace and launches onboarding pipeline."},
    tags=["Workspace", "Create", "Pipeline", "REXT"],
    project_name="REXT"
)
async def create_workspace(
    data: WorkspaceSchema,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
    _: None = Depends(check_workspace_limit()),
):
    """
    Create a new workspace for the current user.

    Returns immediately with workspace metadata and an operation identifier that
    can be used to subscribe to Server-Sent Events for background processing
    progress.
    """
    if not data.name:
        raise RextValidationException(
            message="Workspace name is required",
            field_errors={"name": ["Name must be provided"]},
        )

    if not data.url:
        raise RextValidationException(
            message="Workspace URL is required",
            field_errors={"url": ["URL must be provided and valid"]},
        )

    user_id = UUID(str(current_user.get("identity")))
    with trace(name="Workspace Creation", inputs=data.model_dump()):
        service = WorkspaceService(db)
        result = await service.create_workspace_for_user(
            user_id=user_id,
            name=data.name,
            timezone=data.timezone,
            url=str(data.url),
        )

    return created(
        data=result,
        request=request,
        message="Workspace created successfully. Background processing initiated.",
    )


@router.delete("/delete")
@require_permissions("workspace.delete")
@db_transaction_handler("delete workspace", auto_commit=True)
async def delete_workspace(
    workspace_id: str,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Delete a workspace owned or joined by the current user.
    
    Args:
        workspace_id: Workspace UUID (query parameter)
    """
    user_id = UUID(str(current_user.get("identity")))
    workspace_uuid = UUID(workspace_id)

    service = WorkspaceService(db)
    await service.delete_workspace_for_user(workspace_uuid, user_id)

    return success(
        data={},
        request=request,
        message="Workspace deleted successfully",
    )


@router.put("/update")
@require_permissions("workspace.update")
@db_transaction_handler("update workspace", auto_commit=True)
async def update_workspace(
    workspace_id: str,
    data: WorkspaceSchema,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Update workspace metadata for the current user.
    
    Args:
        workspace_id: Workspace UUID (query parameter)
    """
    user_id = UUID(str(current_user.get("identity")))
    workspace_uuid = UUID(workspace_id)

    service = WorkspaceService(db)
    workspace = await service.update_workspace_for_user(
        workspace_id=workspace_uuid,
        user_id=user_id,
        name=data.name,
        timezone=data.timezone,
        url=str(data.url) if data.url else None,
    )

    return success(
        data={"workspace": workspace},
        request=request,
        message="Workspace updated successfully",
    )
