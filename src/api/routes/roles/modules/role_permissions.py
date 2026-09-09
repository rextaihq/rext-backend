"""Role permission assignment module."""

from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.database.async_database import get_async_db
from src.api.models.user_models.permissions import Permission
from src.api.models.user_models.role_permissions import RolePermission
from src.api.schema.response.rbac_responses import AssignPermissionsData, RevokePermissionData
from src.api.schema.response_schemas import SuccessResponse
from src.api.schema.role_schema import AssignPermissionsRequest
from src.api.security.dependencies import get_current_user
from src.services.permission_service import PermissionService
from src.utils.audit_helper import create_audit_log_async
from src.utils.logger import logger
from src.utils.response_utils import success
from src.utils.route_decorators import db_transaction_handler, require_permissions

router = APIRouter()


@router.post("/{role_id}/permissions", response_model=SuccessResponse[AssignPermissionsData])
@require_permissions("role.manage_permissions", workspace_scoped=False)
@db_transaction_handler("assign permissions to role", auto_commit=True)
async def assign_permissions_to_role(
    request: Request,
    role_id: str,
    assignment_data: AssignPermissionsRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
):
    """Assign permissions to a role."""
    service = PermissionService(db)
    permission_ids = [UUID(permission_id) for permission_id in assignment_data.permission_ids]
    result = await service.assign_permissions_to_role(
        role_id=UUID(role_id), permission_ids=permission_ids
    )

    user_id = current_user.get("identity")
    await create_audit_log_async(
        db=db,
        user_id=UUID(user_id),
        action="permission.assign",
        resource_type="role",
        resource_id=role_id,
        old_values=None,
        new_values={
            "permission_ids": [str(pid) for pid in permission_ids],
            "added_count": result["added_count"],
            "skipped_count": result["skipped_count"],
            "invalid_count": result["invalid_count"],
        },
        request=request,
        metadata={
            "role_name": result.get("role_name"),
            "performed_by_email": current_user.get("email"),
            "operation": "assign",
        },
    )

    logger.info(
        f"Permission assignment logged to audit for role {result.get('role_name')}",
        extra={"role_id": role_id, "added_count": result["added_count"], "performed_by": user_id},
    )

    return success(
        data=result,
        request=request,
        message=f"Added {result['added_count']} permission(s) to role '{result['role_name']}'",
    )


@router.put("/{role_id}/permissions", response_model=SuccessResponse[AssignPermissionsData])
@require_permissions("role.manage_permissions", workspace_scoped=False)
@db_transaction_handler("update role permissions", auto_commit=True)
async def update_role_permissions(
    request: Request,
    role_id: str,
    assignment_data: AssignPermissionsRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
):
    """Atomically update/replace permissions assigned to a role."""
    from src.services.role_service import RoleService

    # Capture old permission IDs before the update
    old_perms_result = await db.execute(
        select(RolePermission.permission_id).where(RolePermission.role_id == UUID(role_id))
    )
    old_permission_ids = [str(row[0]) for row in old_perms_result.all()]

    role_service = RoleService(db)
    permission_ids = [UUID(permission_id) for permission_id in assignment_data.permission_ids]
    updated_role = await role_service.update_role_permissions(
        role_id=UUID(role_id),
        permission_ids=permission_ids,
    )

    new_permission_ids = [str(pid) for pid in permission_ids]
    added = set(new_permission_ids) - set(old_permission_ids)
    removed = set(old_permission_ids) - set(new_permission_ids)

    # Resolve names for everything touched. Storing only UUIDs makes the audit
    # trail unreadable — a reviewer cannot tell "audit.read" from "role.delete"
    # by id, which is the whole point of the log.
    touched_ids = [UUID(pid) for pid in (added | removed)]
    permission_names: dict[str, str] = {}
    if touched_ids:
        name_rows = await db.execute(
            select(Permission.id, Permission.name).where(Permission.id.in_(touched_ids))
        )
        permission_names = {str(row[0]): row[1] for row in name_rows.all()}

    def _names(ids) -> list[str]:
        """Names for a set of permission ids, falling back to the id."""
        return sorted(permission_names.get(pid, pid) for pid in ids)

    added_names = _names(added)
    removed_names = _names(removed)

    user_id = current_user.get("identity")
    await create_audit_log_async(
        db=db,
        user_id=UUID(user_id),
        action="permission.update",
        resource_type="role",
        resource_id=role_id,
        old_values={
            "permission_ids": old_permission_ids,
            "permission_count": len(old_permission_ids),
        },
        new_values={
            "permission_ids": new_permission_ids,
            "permission_count": len(new_permission_ids),
            "added_count": len(added),
            "removed_count": len(removed),
            "added_permissions": added_names,
            "removed_permissions": removed_names,
        },
        request=request,
        # Denormalised onto the row itself, not just metadata: the audit UI
        # reads user_email directly and showed "System" for every entry while
        # it was only buried in metadata.
        user_email=current_user.get("email"),
        full_name=current_user.get("full_name"),
        metadata={
            "role_name": updated_role.name,
            "role_display_name": updated_role.display_name,
            "performed_by_email": current_user.get("email"),
            "operation": "update",
            "added_ids": list(added),
            "removed_ids": list(removed),
            "added_permissions": added_names,
            "removed_permissions": removed_names,
        },
    )

    logger.info(
        f"Permission update logged to audit for role {updated_role.display_name}",
        extra={
            "role_id": role_id,
            "old_count": len(old_permission_ids),
            "new_count": len(new_permission_ids),
            "performed_by": user_id,
        },
    )

    return success(
        data={
            "role_id": str(updated_role.id),
            "role_name": updated_role.name,
            "added_count": len(permission_ids),
            "skipped_count": 0,
            "invalid_count": 0,
        },
        request=request,
        message=f"Updated permissions for role '{updated_role.display_name}'",
    )


@router.delete(
    "/{role_id}/permissions/{permission_id}", response_model=SuccessResponse[RevokePermissionData]
)
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

    user_id = current_user.get("identity")
    await create_audit_log_async(
        db=db,
        user_id=UUID(user_id),
        action="permission.revoke",
        resource_type="role",
        resource_id=role_id,
        old_values={
            "permission_id": permission_id,
            "permission_name": result.get("permission_name"),
        },
        new_values=None,
        request=request,
        metadata={
            "role_name": result.get("role_name"),
            "performed_by_email": current_user.get("email"),
            "operation": "revoke",
            "revoked_permission_id": permission_id,
            "revoked_permission_name": result.get("permission_name"),
        },
    )

    logger.info(
        f"Permission revoke logged to audit for role {result.get('role_name')}",
        extra={"role_id": role_id, "permission_id": permission_id, "performed_by": user_id},
    )

    return success(
        data=result,
        request=request,
        message="Permission revoked from role",
    )
