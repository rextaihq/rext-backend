from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from .workspace_core import router as core_router, get_workspaces, get_workspace_by_slug, get_workspace_by_id_path
from .workspace_members import router as members_router
from .workspace_knowledge import router as knowledge_router
from .workspace_brand_voice import router as brand_voice_router
from src.api.database.async_database import get_async_db
from src.api.schema.workspace_schema import WorkspaceSchema
from src.api.security.dependencies import get_current_user
from src.services.workspace_service import WorkspaceService
from src.utils.response_utils import created, success
from src.utils.route_decorators import db_transaction_handler
from src.api.middleware.exceptions import WrextValidationException

router = APIRouter(prefix="/workspace", tags=["workspace"])

router.include_router(core_router)
router.include_router(members_router)
router.include_router(knowledge_router)
router.include_router(brand_voice_router)

# Add alias routes for frontend compatibility (plural "workspaces" vs singular "workspace")
# This allows the frontend to call either endpoint with RESTful conventions
workspaces_router = APIRouter(prefix="/workspaces", tags=["workspace"])

# GET endpoints
workspaces_router.add_api_route("", get_workspaces, methods=["GET"], name="get_workspaces_alias")
workspaces_router.add_api_route("/slug/{workspace_slug}", get_workspace_by_slug, methods=["GET"], name="get_workspace_by_slug_alias")
workspaces_router.add_api_route("/{workspace_id}", get_workspace_by_id_path, methods=["GET"], name="get_workspace_by_id_restful")


# POST/PUT/DELETE endpoints - RESTful wrappers
@workspaces_router.post("")
@db_transaction_handler("create workspace", auto_commit=True)
async def create_workspace_restful(
    data: WorkspaceSchema,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
):
    """Create a new workspace for the current user (RESTful endpoint)."""
    if not data.name:
        raise WrextValidationException(
            message="Workspace name is required",
            field_errors={"name": ["Name must be provided"]},
        )

    if not data.url:
        raise WrextValidationException(
            message="Workspace URL is required",
            field_errors={"url": ["URL must be provided and valid"]},
        )

    user_id = UUID(str(current_user.get("identity")))
    service = WorkspaceService(db)
    workspace = await service.create_workspace_for_user(
        user_id=user_id,
        name=data.name,
        description=data.description,
        url=str(data.url),
    )

    return created(
        data={"workspace": workspace},
        request=request,
        message="Workspace created successfully",
    )


@workspaces_router.put("/{workspace_id}")
@db_transaction_handler("update workspace", auto_commit=True)
async def update_workspace_restful(
    workspace_id: str,
    data: WorkspaceSchema,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
):
    """Update workspace metadata (RESTful endpoint with path parameter)."""
    user_id = UUID(str(current_user.get("identity")))
    workspace_uuid = UUID(workspace_id)

    service = WorkspaceService(db)
    workspace = await service.update_workspace_for_user(
        workspace_id=workspace_uuid,
        user_id=user_id,
        name=data.name,
        description=data.description,
        url=str(data.url) if data.url else None,
    )

    return success(
        data={"workspace": workspace},
        request=request,
        message="Workspace updated successfully",
    )


@workspaces_router.delete("/{workspace_id}")
@db_transaction_handler("delete workspace", auto_commit=True)
async def delete_workspace_restful(
    workspace_id: str,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
):
    """Delete a workspace (RESTful endpoint with path parameter)."""
    user_id = UUID(str(current_user.get("identity")))
    workspace_uuid = UUID(workspace_id)

    service = WorkspaceService(db)
    await service.delete_workspace_for_user(workspace_uuid, user_id)

    return success(
        data={},
        request=request,
        message="Workspace deleted successfully",
    )

__all__ = ["router", "workspaces_router"]
