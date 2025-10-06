"""
Role permission assignment module.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime

from src.api.database.async_database import get_async_db
from src.api.security.dependencies import get_current_user
from src.utils.route_decorators import db_transaction_handler, require_permissions
from src.api.models.user_models.roles import Role
from src.api.models.user_models.role_permissions import RolePermission
from src.api.models.user_models.permissions import Permission
from src.api.schema.role_schema import AssignPermissionsRequest
from src.utils.response_utils import success
from src.utils.route_decorators import db_transaction_handler
from src.api.middleware.exceptions import ResourceNotFoundException, WrextAPIException
from src.utils.logger import logger
from .helpers import check_role_permission


router = APIRouter()


@router.post("/{role_id}/permissions", response_model=dict)
@db_transaction_handler("assign permissions to role", auto_commit=True)
async def assign_permissions_to_role(
    request: Request,
    role_id: str,
    assignment_data: AssignPermissionsRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Assign permissions to a role.

    Requires: role.manage_permissions permission OR admin role

    Parameters:
    - role_id: UUID of the role

    Request Body:
    - permission_ids: List of permission UUIDs to assign

    Returns:
    - Count of permissions added
    """
    # Check permission
    user_id = current_user.get("identity")
    await check_role_permission(db, user_id, "role.manage_permissions")

    # Verify role exists
    result = await db.execute(select(Role).where(Role.id == role_id))
    role = result.scalar_one_or_none()
    if not role:
        raise ResourceNotFoundException(
            message="Role not found",
            context={"role_id": role_id}
        )

    # Get existing permission assignments
    result = await db.execute(
        select(RolePermission.permission_id).where(
            RolePermission.role_id == role_id
        )
    )
    existing_perms = result.all()
    existing_perm_ids = {str(perm[0]) for perm in existing_perms}

    # Add new permissions
    added_count = 0
    skipped_count = 0
    invalid_count = 0

    for perm_id in assignment_data.permission_ids:
        # Skip if already assigned
        if perm_id in existing_perm_ids:
            skipped_count += 1
            continue

        # Verify permission exists
        result = await db.execute(select(Permission).where(Permission.id == perm_id))
        permission = result.scalar_one_or_none()
        if not permission:
            logger.warning(f"Permission {perm_id} not found, skipping")
            invalid_count += 1
            continue

        # Create assignment
        role_perm = RolePermission(
            role_id=role_id,
            permission_id=perm_id,
            created_at=datetime.utcnow()
        )
        db.add(role_perm)
        added_count += 1

    logger.info(
        f"Added {added_count} permissions to role '{role.name}' "
        f"(skipped {skipped_count} existing, {invalid_count} invalid) "
        f"by user {user_id}"
    )

    return {
        "data": {
            "role_id": str(role_id),
            "role_name": role.name,
            "added_count": added_count,
            "skipped_count": skipped_count,
            "invalid_count": invalid_count
        },
        "message": f"Added {added_count} permission(s) to role '{role.display_name}'"
    }


@router.delete("/{role_id}/permissions/{permission_id}", response_model=dict)
@db_transaction_handler("revoke permission from role", auto_commit=True)
@require_permissions("role.manage_permissions", workspace_scoped=False)
async def revoke_permission_from_role(
    request: Request,
    role_id: str,
    permission_id: str,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Revoke a permission from a role.

    Requires: role.manage_permissions permission OR admin role

    Parameters:
    - role_id: UUID of the role
    - permission_id: UUID of the permission to revoke

    Returns:
    - Success message
    """
    # Check permission
    user_id = current_user.get("identity")
    await check_role_permission(db, user_id, "role.manage_permissions")

    # Find the role-permission assignment
    result = await db.execute(
        select(RolePermission).where(
            RolePermission.role_id == role_id,
            RolePermission.permission_id == permission_id
        )
    )
    role_perm = result.scalar_one_or_none()

    if not role_perm:
        raise ResourceNotFoundException(
            message="Permission assignment not found",
            context={"role_id": role_id, "permission_id": permission_id}
        )

    # Get role and permission names for logging
    result = await db.execute(select(Role).where(Role.id == role_id))
    role = result.scalar_one_or_none()
    result = await db.execute(select(Permission).where(Permission.id == permission_id))
    permission = result.scalar_one_or_none()

    await db.delete(role_perm)

    logger.info(
        f"Revoked permission '{permission.name if permission else permission_id}' "
        f"from role '{role.name if role else role_id}' by user {user_id}"
    )

    return {
        "data": {
            "role_id": str(role_id),
            "permission_id": str(permission_id),
            "role_name": role.name if role else None,
            "permission_name": permission.name if permission else None
        },
        "message": f"Permission revoked from role"
    }
