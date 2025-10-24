"""
User Permissions API endpoint.

Provides permission information for the current user to support frontend
permission-based UI rendering.
"""

from fastapi import APIRouter, Depends, Request, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
from uuid import UUID

from src.api.database.async_database import get_async_db
from src.api.security.dependencies import get_current_user
from src.utils.rbac_utils import get_user_permissions, get_user_roles
from src.utils.workspace_utils import async_get_workspace_id_from_identifier
from src.utils.response_utils import success
from src.utils.logger import logger
from src.utils.route_decorators import require_permissions


router = APIRouter()


@router.get("/me/permissions", response_model=dict)
@require_permissions("permission.read")
async def get_current_user_permissions(
    request: Request,
    workspace_id: Optional[str] = Query(None, description="Workspace ID or slug for workspace-scoped permissions"),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get permissions for the current user.

    Returns all permissions that the current user has access to, either
    globally or within a specific workspace.

    **Frontend Usage:**
    This endpoint is used by the frontend to conditionally render UI elements
    based on user permissions (e.g., hide "Delete" button if user lacks
    content.delete permission).

    **Important:** Frontend permission checks are for UX only. The backend
    MUST enforce all permissions via the @require_permissions decorator.

    Query Parameters:
        - workspace_id: Optional workspace UUID or slug. If provided, returns
                       permissions for that workspace + global permissions.
                       If not provided, returns only global permissions.

    Returns:
        {
            "permissions": ["content.create", "content.read", ...],
            "roles": [
                {"name": "editor", "workspace_id": "uuid-or-null"},
                {"name": "admin", "workspace_id": null}
            ],
            "workspace_id": "uuid-or-null"
        }

    Example:
        GET /api/v1/users/me/permissions?workspace_id=abc-123

        Response:
        {
            "status": "success",
            "data": {
                "permissions": [
                    "content.create",
                    "content.read",
                    "content.update",
                    "content.delete",
                    "content.publish",
                    "topic.create",
                    ...
                ],
                "roles": [
                    {"name": "editor", "workspace_id": "abc-123"}
                ],
                "workspace_id": "abc-123"
            }
        }
    """
    user_id = UUID(current_user.get("identity"))

    # Resolve workspace ID if provided
    workspace_uuid = None
    if workspace_id:
        workspace_uuid = await async_get_workspace_id_from_identifier(db, workspace_id)
        logger.debug(f"Fetching permissions for user {user_id} in workspace {workspace_uuid}")
    else:
        logger.debug(f"Fetching global permissions for user {user_id}")

    # Get user's permissions
    permissions = await get_user_permissions(db, user_id, workspace_uuid)

    # Get user's roles (includes workspace scope information)
    roles = await get_user_roles(db, user_id, workspace_uuid)

    # Format roles for response
    roles_data = [
        {
            "name": role.name,
            "display_name": role.display_name,
            "hierarchy_level": role.hierarchy_level,
            "workspace_id": str(ws_id) if ws_id else None
        }
        for role, ws_id in roles
    ]

    logger.info(
        f"User {user_id} has {len(permissions)} permissions "
        f"and {len(roles)} role(s) in workspace {workspace_uuid or 'global'}"
    )

    return success(
        data={
            "permissions": permissions,
            "roles": roles_data,
            "workspace_id": str(workspace_uuid) if workspace_uuid else None
        },
        message="User permissions retrieved successfully",
        request=request
    )
