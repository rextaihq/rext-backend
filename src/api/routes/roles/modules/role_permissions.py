
"""Role permission assignment module."""

from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.database.async_database import get_async_db
from src.api.schema.role_schema import AssignPermissionsRequest
from src.api.security.dependencies import get_current_user
from src.services.permission_service import PermissionService
from src.utils.response_utils import success
from src.utils.route_decorators import db_transaction_handler, require_permissions
from .helpers import check_role_permission

router = APIRouter()


@router.post("/{role_id}/permissions", response_model=dict)
@require_permissions(["role.manage_permissions"])
@db_transaction_handler("assign permissions to role", auto_commit=True)
async def assign_permissions_to_role(
    request: Request,
    role_id: str,
    assignment_data: AssignPermissionsRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
):
    """Assign permissions to a role."""
    user_id = UUID(str(current_user.get("identity")))
    await check_role_permission(db, user_id, "role.manage_permissions")

    service = PermissionService(db)
    permission_ids = [UUID(permission_id) for permission_id in assignment_data.permission_ids]
    result = await service.assign_permissions_to_role(role_id=UUID(role_id), permission_ids=permission_ids)

    return success(
        data=result,
        request=request,
        message=f"Added {result['added_count']} permission(s) to role '{result['role_name']}'",
    )


@router.delete("/{role_id}/permissions/{permission_id}", response_model=dict)
@db_transaction_handler("revoke permission from role", auto_commit=True)
@require_permissions("role.manage_permissions", workspace_scoped=False)
async def revoke_permission_from_role(
    request: Request,
    role_id: str,
    permission_id: str,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
):
    """Revoke a permission from a role."""
    service = PermissionService(db)
    result = await service.revoke_permission_from_role(
        role_id=UUID(role_id),
        permission_id=UUID(permission_id),
    )

    return success(
        data=result,
        request=request,
        message="Permission revoked from role",
    )
