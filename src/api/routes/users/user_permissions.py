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
from src.utils.logger import logger
from src.utils.route_decorators import require_permissions, db_transaction_handler


router = APIRouter()


@router.get("/me/permissions", response_model=dict)
@require_permissions("permission.read", workspace_scoped=False)
@db_transaction_handler("get user permissions", auto_commit=False)
async def get_current_user_permissions(
    request: Request,
    workspace_id: Optional[str] = Query(None, description="Workspace ID or slug for workspace-scoped permissions"),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get permissions for the current user.
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

    return {
        "permissions": permissions,
        "roles": roles_data,
        "workspace_id": str(workspace_uuid) if workspace_uuid else None
    }
