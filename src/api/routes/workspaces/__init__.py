from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from .workspace_core import router as core_router, get_workspaces, get_workspace_by_slug, get_workspace_by_id_path
from .workspace_brand_voice import router as brand_voice_router
from .workspace_personas import router as personas_router
from .workspace_members import router as members_router
from .workspace_invitations import router as invitations_router
from .workspace_permissions import router as permissions_router
from .workspace_stats import router as stats_router
from src.api.database.async_database import get_async_db
from src.api.models.user_models.roles import Role
from src.api.schema.workspace_schema import WorkspaceSchema
from src.api.security.dependencies import get_current_user
from src.services.workspace_service import WorkspaceService
from src.utils.response_utils import created, success
from src.utils.route_decorators import db_transaction_handler, require_permissions
from src.api.middleware.exceptions import RextValidationException
from src.api.middleware.usage_limiter import check_workspace_limit

router = APIRouter(prefix="/workspace", tags=["workspace"])

router.include_router(core_router)
# Add alias routes for frontend compatibility (plural "workspaces" vs singular "workspace")
# This allows the frontend to call either endpoint with RESTful conventions
workspaces_router = APIRouter(prefix="/workspaces", tags=["workspace"])
workspaces_router.include_router(brand_voice_router)
workspaces_router.include_router(personas_router)
workspaces_router.include_router(members_router)
workspaces_router.include_router(invitations_router)
workspaces_router.include_router(permissions_router)
workspaces_router.include_router(stats_router)

# GET endpoints - ORDER MATTERS! More specific routes must come before parameterized routes
workspaces_router.add_api_route("", get_workspaces, methods=["GET"], name="get_workspaces_alias")
workspaces_router.add_api_route("/slug/{workspace_slug}", get_workspace_by_slug, methods=["GET"], name="get_workspace_by_slug_alias")
# Note: /{workspace_id} must be added AFTER all other specific routes to avoid capturing them


# POST/PUT/DELETE endpoints - RESTful wrappers
@workspaces_router.post("")
@require_permissions("workspace.create",  workspace_scoped=False)
@db_transaction_handler("create workspace", auto_commit=True)
async def create_workspace_restful(
    data: WorkspaceSchema,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
    _: None = Depends(check_workspace_limit()),
):
    """
    Create a new workspace for the current user (RESTful endpoint).

    Returns immediately with workspace metadata and an operation identifier for
    tracking background processing via SSE.
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
        timezone=data.timezone,
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


@workspaces_router.get("/available-roles")
@db_transaction_handler("get available roles", auto_commit=False)
async def get_available_roles(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Get available roles for workspace member invitations.

    Returns workspace roles that can be assigned to workspace members.
    Uses is_workspace_role flag for proper role classification.
    """
    # Fetch all workspace roles ordered by hierarchy
    query = (
        select(Role)
        .where(Role.is_workspace_role == True)
        .order_by(Role.hierarchy_level.desc())
    )
    result = await db.execute(query)
    roles = result.scalars().all()

    roles_data = [
        {
            "id": str(role.id),
            "name": role.name,
            "display_name": role.display_name,
            "description": role.description,
            "is_system_role": role.is_system_role,
            "is_workspace_role": role.is_workspace_role,
            "hierarchy_level": role.hierarchy_level,
            "created_at": role.created_at.isoformat() if role.created_at else None,
            "updated_at": role.updated_at.isoformat() if role.updated_at else None,
        }
        for role in roles
    ]

    return success(
        data={"roles": roles_data, "total_count": len(roles_data)},
        request=request,
        message=f"Retrieved {len(roles_data)} available role(s)",
    )


# Add parameterized routes LAST to avoid capturing specific routes
workspaces_router.add_api_route("/{workspace_id}", get_workspace_by_id_path, methods=["GET"], name="get_workspace_by_id_restful")

__all__ = ["router", "workspaces_router"]
