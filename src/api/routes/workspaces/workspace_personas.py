from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.database.async_database import get_async_db
from src.api.security.dependencies import get_current_user
from src.services.workspace_permission_service import WorkspacePermissionService
from src.utils.rbac_utils import get_user_permissions, get_user_roles
from src.utils.response_utils import success
from src.utils.workspace_utils import async_get_workspace_id_from_identifier
from src.utils.logger import logger
from src.utils.route_decorators import require_permissions

router = APIRouter(tags=["Workspace Permissions"])


@router.get("/{workspace_id}/permissions/me")
@require_permissions("member.read", workspace_scoped=True)
async def get_my_workspace_permissions(
    workspace_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    user_id = UUID(user["identity"])

    try:
        workspace_uuid = UUID(workspace_id)
    except ValueError:
        workspace_uuid = await async_get_workspace_id_from_identifier(db, workspace_id)

    result = await WorkspacePermissionService.get_user_workspace_permissions(
        db, user_id, workspace_uuid
    )

    return success(
        data=result,
        message="Workspace permissions retrieved successfully",
    )


@router.get("/{workspace_id}/permissions/check")
@require_permissions("member.read", workspace_scoped=True)
async def check_workspace_permission(
    workspace_id: str,
    permission: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    user_id = UUID(user["identity"])

    try:
        workspace_uuid = UUID(workspace_id)
    except ValueError:
        workspace_uuid = await async_get_workspace_id_from_identifier(db, workspace_id)

    has_permission = await WorkspacePermissionService.check_user_permission(
        db, user_id, workspace_uuid, permission
    )

    return success(
        data={
            "has_permission": has_permission,
            "permission": permission,
            "workspace_id": str(workspace_uuid),
        },
        message="Permission check completed",
    )


@router.post("/{workspace_id}/permissions/refresh")
@require_permissions("member.read", workspace_scoped=True)
async def refresh_workspace_permissions(
    workspace_id: str,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    return await get_my_workspace_permissions(workspace_id, user, db)
