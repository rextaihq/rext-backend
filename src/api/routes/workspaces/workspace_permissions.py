"""
Workspace Permission Routes

Provides endpoints for checking and retrieving user permissions within specific workspaces.
These endpoints are critical for frontend permission checks in a multi-tenant environment.
"""

from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from langgraph_sdk import Auth

from src.api.database.async_database import get_async_db
from src.api.security.dependencies import get_current_user
from src.services.workspace_permission_service import WorkspacePermissionService
from src.utils.rbac_utils import (
    check_permission,
    get_user_permissions,
    get_user_roles
)
from src.utils.response_utils import success
from src.utils.workspace_utils import async_get_workspace_id_from_identifier
from src.utils.logger import logger
from src.utils.route_decorators import require_permissions

router = APIRouter(
    prefix="",
    tags=["Workspace Permissions"]
)


@router.get("/{workspace_id}/permissions/me")
@require_permissions(["member.read"], workspace_scoped=True)
async def get_my_workspace_permissions(
    workspace_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Get current user's permissions in a specific workspace.

    This endpoint returns all permissions the authenticated user has within
    the specified workspace, using the new WorkspacePermissionService.

    **Multi-Tenancy**: This is critical for proper permission checking in a multi-tenant
    application. Users may have different permissions in different workspaces.

    **Permission Format**: Uses dot notation (e.g., "content.create", "topic.read")

    Args:
        workspace_id: Workspace UUID or slug
        user: Current authenticated user (from JWT)
        db: Database session

    Returns:
        {
            "workspace_id": "uuid",
            "workspace_slug": "slug",
            "user_role": "workspace_owner",
            "permissions": [
                "content.create",
                "content.read",
                "content.update",
                "topic.read"
            ]
        }

    Example:
        GET /api/v1/workspaces/abc-123/permissions/me
        Authorization: Bearer <token>

    Frontend Usage:
        const { data } = await fetch('/workspaces/abc-123/permissions/me');
        // Store permissions in frontend state
        // Use for permission guards and UI rendering
    """
    try:
        user_id = UUID(user["identity"])

        # Resolve workspace ID (handles both UUID and slug)
        try:
            workspace_uuid = UUID(workspace_id)
        except ValueError:
            workspace_uuid = await async_get_workspace_id_from_identifier(db, workspace_id)

        # Use new WorkspacePermissionService for consistent permission loading
        result = await WorkspacePermissionService.get_user_workspace_permissions(
            db, user_id, workspace_uuid
        )

        logger.info(
            f"Retrieved workspace permissions for user {user_id} in workspace {workspace_uuid}",
            extra={
                "user_id": str(user_id),
                "workspace_id": str(workspace_uuid),
                "permission_count": len(result["permissions"]),
                "user_role": result["user_role"]
            }
        )

        return success(
            data=result,
            message="Workspace permissions retrieved successfully"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Error retrieving workspace permissions: {str(e)}",
            extra={
                "user_id": user.get("identity"),
                "workspace_id": workspace_id
            }
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve workspace permissions"
        )


@router.get("/{workspace_id}/permissions/check")
@require_permissions(["member.read"], workspace_scoped=True)
async def check_workspace_permission(
    workspace_id: str,
    permission: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Check if current user has a specific permission in a workspace.

    This endpoint provides a quick permission check without retrieving all permissions.
    Useful for conditional API calls or real-time permission verification.

    **Permission Format**: Supports both dot notation (content.delete) and colon notation (content:delete)
    for backward compatibility. Dot notation is preferred.

    Args:
        workspace_id: Workspace UUID or slug
        permission: Permission to check (e.g., "content.delete", "workspace.manage_settings")
        user: Current authenticated user (from JWT)
        db: Database session

    Returns:
        {
            "has_permission": true,
            "permission": "content.delete",
            "workspace_id": "uuid"
        }

    Example:
        GET /api/v1/workspaces/abc-123/permissions/check?permission=content.delete
        Authorization: Bearer <token>

    Frontend Usage:
        // Before performing a sensitive action
        const { data } = await fetch(
            '/workspaces/abc-123/permissions/check?permission=content.delete'
        );
        if (data.has_permission) {
            // Allow action
        }
    """
    try:
        user_id = UUID(user["identity"])

        # Resolve workspace ID
        try:
            workspace_uuid = UUID(workspace_id)
        except ValueError:
            workspace_uuid = await async_get_workspace_id_from_identifier(db, workspace_id)

        # Use new WorkspacePermissionService
        has_permission = await WorkspacePermissionService.check_user_permission(
            db, user_id, workspace_uuid, permission
        )

        logger.debug(
            f"Permission check: user={user_id}, permission={permission}, "
            f"workspace={workspace_uuid}, result={has_permission}"
        )

        return success(
            data={
                "has_permission": has_permission,
                "permission": permission,
                "workspace_id": str(workspace_uuid)
            },
            message="Permission check completed"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Error checking workspace permission: {str(e)}",
            extra={
                "user_id": user.get("identity"),
                "workspace_id": workspace_id,
                "permission": permission
            }
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to check workspace permission"
        )


@router.post("/{workspace_id}/permissions/refresh")
@require_permissions(["member.read"], workspace_scoped=True)
async def refresh_workspace_permissions(
    workspace_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Refresh user's workspace permissions.

    Forces a fresh retrieval of permissions from the database. Useful after
    role changes or permission updates.

    Args:
        workspace_id: Workspace UUID or slug
        user: Current authenticated user (from JWT)
        db: Database session

    Returns:
        Updated permissions and roles (same format as /permissions/me)

    Example:
        POST /api/v1/workspaces/abc-123/permissions/refresh
        Authorization: Bearer <token>

    Frontend Usage:
        // After admin changes user's role
        await fetch('/workspaces/abc-123/permissions/refresh', { method: 'POST' });
        // Update permission cache
    """
    # This is essentially the same as get_my_workspace_permissions
    # but with POST method to indicate it's a refresh action
    return await get_my_workspace_permissions(workspace_id, user, db)


@router.get("/{workspace_id}/members/{user_id}/permissions")
@require_permissions(["member.read"], workspace_scoped=True)
async def get_member_workspace_permissions(
    workspace_id: str,
    user_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Get a specific workspace member's permissions.

    This endpoint allows workspace admins to view another user's permissions
    within the workspace. Useful for permission management UI.

    **Authorization**: Requires "workspace:manage_members" permission

    Args:
        workspace_id: Workspace UUID or slug
        user_id: Target user UUID
        current_user: Current authenticated user (from JWT)
        db: Database session

    Returns:
        Same format as /permissions/me but for specified user

    Example:
        GET /api/v1/workspaces/abc-123/members/user-uuid/permissions
        Authorization: Bearer <token>

    Frontend Usage:
        // In member management UI
        const { data } = await fetch(
            `/workspaces/${workspaceId}/members/${userId}/permissions`
        );
        // Display user's permissions in UI
    """
    try:
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
            db,
            current_user_id,
            "workspace:manage_members",
            workspace_uuid,
            "workspace members"
        )

        # Get target user's permissions
        permissions = await get_user_permissions(db, target_user_id, workspace_uuid)
        roles_with_context = await get_user_roles(db, target_user_id, workspace_uuid)

        roles = [
            {
                "name": role.name,
                "display_name": role.display_name,
                "workspace_scoped": ws_id is not None,
                "workspace_id": str(ws_id) if ws_id else None
            }
            for role, ws_id in roles_with_context
        ]

        logger.info(
            f"Admin {current_user_id} viewed permissions for user {target_user_id} "
            f"in workspace {workspace_uuid}"
        )

        return success(
            data={
                "user_id": str(target_user_id),
                "workspace_id": str(workspace_uuid),
                "roles": roles,
                "permissions": list(permissions)
            },
            message="Member permissions retrieved successfully"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Error retrieving member permissions: {str(e)}",
            extra={
                "current_user_id": current_user.get("identity"),
                "target_user_id": user_id,
                "workspace_id": workspace_id
            }
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve member permissions"
        )
