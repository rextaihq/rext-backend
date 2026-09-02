"""
Workspace Permission Routes

Provides endpoints for checking and retrieving user permissions within specific workspaces.
These endpoints are critical for frontend permission checks in a multi-tenant environment.
"""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.database.async_database import get_async_db
from src.api.schema.response.workspace_responses import (
    CheckWorkspacePermissionResponse,
    MemberWorkspacePermissionsResponse,
    MyWorkspacePermissionsResponse,
)
from src.api.schema.response_schemas import SuccessResponse
from src.api.security.dependencies import get_current_user
from src.services.workspace_permission_service import WorkspacePermissionService
from src.utils.logger import logger
from src.utils.rbac_utils import get_user_permissions, get_user_roles
from src.utils.response_utils import success
from src.utils.route_decorators import require_permissions
from src.utils.workspace_utils import async_get_workspace_id_from_identifier

router = APIRouter(prefix="", tags=["Workspace Permissions"])


@router.get(
    "/{workspace_id}/permissions/me", response_model=SuccessResponse[MyWorkspacePermissionsResponse]
)
@require_permissions("member.read", workspace_scoped=True)
async def get_my_workspace_permissions(
    workspace_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Get current user's permissions in a specific workspace.
    """
    user_id = UUID(user["identity"])

    # Resolve workspace ID (UUID or slug)
    try:
        workspace_uuid = UUID(workspace_id)
    except ValueError:
        workspace_uuid = await async_get_workspace_id_from_identifier(db, workspace_id)

    # Service raises custom exceptions → handled globally
    result = await WorkspacePermissionService.get_user_workspace_permissions(
        db, user_id, workspace_uuid
    )

    logger.info(
        "Retrieved workspace permissions",
        extra={
            "user_id": str(user_id),
            "workspace_id": str(workspace_uuid),
            "permission_count": len(result["permissions"]),
            "user_role": result["user_role"],
        },
    )

    return success(data=result, message="Workspace permissions retrieved successfully")


@router.get(
    "/{workspace_id}/permissions/check",
    response_model=SuccessResponse[CheckWorkspacePermissionResponse],
)
@require_permissions("member.read", workspace_scoped=True)
async def check_workspace_permission(
    workspace_id: str,
    permission: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Check if current user has a specific permission in a workspace.
    """
    user_id = UUID(user["identity"])

    # Resolve workspace ID
    try:
        workspace_uuid = UUID(workspace_id)
    except ValueError:
        workspace_uuid = await async_get_workspace_id_from_identifier(db, workspace_id)

    # Use WorkspacePermissionService
    has_permission = await WorkspacePermissionService.check_user_permission(
        db, user_id, workspace_uuid, permission
    )

    logger.debug(
        "Permission check completed",
        extra={
            "user_id": str(user_id),
            "permission": permission,
            "workspace_id": str(workspace_uuid),
            "result": has_permission,
        },
    )

    return success(
        data={
            "has_permission": has_permission,
            "permission": permission,
            "workspace_id": str(workspace_uuid),
        },
        message="Permission check completed",
    )


@router.post(
    "/{workspace_id}/permissions/refresh",
    response_model=SuccessResponse[MyWorkspacePermissionsResponse],
)
@require_permissions("member.read", workspace_scoped=True)
async def refresh_workspace_permissions(
    workspace_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Refresh user's workspace permissions.
    """
    # This is essentially the same as get_my_workspace_permissions
    # but with POST method to indicate it's a refresh action
    return await get_my_workspace_permissions(workspace_id=workspace_id, user=user, db=db)


@router.get(
    "/{workspace_id}/members/{user_id}/permissions",
    response_model=SuccessResponse[MemberWorkspacePermissionsResponse],
)
@require_permissions("member.read", workspace_scoped=True)
async def get_member_workspace_permissions(
    workspace_id: str,
    user_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Get a specific workspace member's permissions.
    """
    current_user_id = UUID(current_user["identity"])
    target_user_id = UUID(user_id)

    # Resolve workspace ID
    try:
        workspace_uuid = UUID(workspace_id)
    except ValueError:
        workspace_uuid = await async_get_workspace_id_from_identifier(db, workspace_id)

    # Check if current user has permission to view other members' permissions
    from src.utils.rbac_utils import require_permission

    await require_permission(
        db, current_user_id, "workspace.manage_members", workspace_uuid, "workspace members"
    )

    # Get target user's permissions
    permissions = await get_user_permissions(db, target_user_id, workspace_uuid)
    roles_with_context = await get_user_roles(db, target_user_id, workspace_uuid)

    roles = [
        {
            "name": role.name,
            "display_name": role.display_name,
            "workspace_scoped": ws_id is not None,
            "workspace_id": str(ws_id) if ws_id else None,
        }
        for role, ws_id in roles_with_context
    ]

    logger.info(
        "Admin viewed member permissions",
        extra={
            "current_user_id": str(current_user_id),
            "target_user_id": str(target_user_id),
            "workspace_id": str(workspace_uuid),
        },
    )

    return success(
        data={
            "user_id": str(target_user_id),
            "workspace_id": str(workspace_uuid),
            "roles": roles,
            "permissions": list(permissions),
        },
        message="Member permissions retrieved successfully",
    )
