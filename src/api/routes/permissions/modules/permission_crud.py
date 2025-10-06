"""
Permission CRUD operations module.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select
from typing import Optional

from src.api.database.async_database import get_async_db
from src.api.security.dependencies import get_current_user
from src.api.models.user_models.permissions import Permission
from src.api.models.user_models.role_permissions import RolePermission
from src.api.models.user_models.roles import Role
from src.api.schema.permission_schema import (
    PermissionCreate,
    PermissionUpdate,
)
from src.utils.response_utils import success, created
from src.utils.db_utils import get_or_404, ensure_unique
from src.api.middleware.exceptions import (
    DuplicateResourceException,
    WrextValidationException,
    ResourceNotFoundException,
    WrextAPIException
)
from src.utils.logger import logger
from src.utils.route_decorators import db_transaction_handler, require_permissions
from .helpers import check_permission_access


router = APIRouter()


@router.get("/", response_model=dict)
@db_transaction_handler("list permissions", auto_commit=False)
async def list_permissions(
    request: Request,
    resource: Optional[str] = Query(None, description="Filter by resource type"),
    include_roles: bool = Query(False, description="Include roles for each permission"),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    List all permissions.

    Requires: permission.read permission OR admin role

    Query Parameters:
    - resource: Filter permissions by resource type
    - include_roles: If true, include roles for each permission

    Returns:
    - List of permissions
    """
    # Check permission
    user_id = current_user.get("identity")
    await check_permission_access(db, user_id, "permission.read")

    # Query permissions
    query = select(Permission)

    # Filter by resource if provided
    if resource:
        query = query.where(Permission.resource == resource)

    result = await db.execute(query.order_by(Permission.resource, Permission.action))
    permissions = result.scalars().all()

    # Format response
    if include_roles:
        permissions_data = []
        for perm in permissions:
            # Get roles that have this permission
            result = await db.execute(
                select(Role)
                .join(RolePermission, RolePermission.role_id == Role.id)
                .where(RolePermission.permission_id == perm.id)
            )
            roles = result.scalars().all()

            perm_dict = perm.to_dict()
            perm_dict["roles"] = [
                {
                    "id": str(role.id),
                    "name": role.name,
                    "display_name": role.display_name,
                    "hierarchy_level": role.hierarchy_level
                }
                for role in roles
            ]
            permissions_data.append(perm_dict)
    else:
        permissions_data = [perm.to_dict() for perm in permissions]

    return {
        "data": {"permissions": permissions_data, "count": len(permissions_data)},
        "message": f"Retrieved {len(permissions_data)} permissions"
    }


@router.get("/{permission_id}", response_model=dict)
@db_transaction_handler("get permission", auto_commit=False)
async def get_permission(
    request: Request,
    permission_id: str,
    include_roles: bool = Query(False, description="Include roles"),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get a specific permission by ID.

    Requires: permission.read permission OR admin role

    Parameters:
    - permission_id: UUID of the permission

    Query Parameters:
    - include_roles: If true, include roles that have this permission

    Returns:
    - Permission details with optional roles
    """
    # Check permission
    user_id = current_user.get("identity")
    await check_permission_access(db, user_id, "permission.read")

    # Get permission (using db_utils)
    permission = await get_or_404(db, Permission, permission_id, "permission")

    perm_data = permission.to_dict()

    # Include roles if requested
    if include_roles:
        result = await db.execute(
            select(Role)
            .join(RolePermission, RolePermission.role_id == Role.id)
            .where(RolePermission.permission_id == permission.id)
        )
        roles = result.scalars().all()

        perm_data["roles"] = [
            {
                "id": str(role.id),
                "name": role.name,
                "display_name": role.display_name,
                "hierarchy_level": role.hierarchy_level
            }
            for role in roles
        ]

    return {
        "data": {"permission": perm_data},
        "message": "Permission retrieved successfully"
    }


@router.post("/", response_model=dict, status_code=status.HTTP_201_CREATED)
@db_transaction_handler("create permission", auto_commit=True)
@require_permissions("permission.create", workspace_scoped=False)
async def create_permission(
    request: Request,
    permission_data: PermissionCreate,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Create a new permission.

    Requires: permission.create permission OR admin role

    Request Body:
    - name: Unique permission name (format: resource.action)
    - display_name: Human-readable name
    - description: Optional description
    - resource: Resource type (e.g., "user", "role")
    - action: Action type (e.g., "read", "create")

    Returns:
    - Created permission details
    """
    # Check permission
    user_id = current_user.get("identity")
    await check_permission_access(db, user_id, "permission.create")

    # Check if permission name already exists (case-insensitive)
    result = await db.execute(
        select(Permission).where(
            func.lower(Permission.name) == permission_data.name.lower()
        )
    )
    existing_perm = result.scalar_one_or_none()

    if existing_perm:
        raise DuplicateResourceException(
            message="Permission with this name already exists",
            context={"name": permission_data.name}
        )

    # Validate name matches resource.action format
    expected_name = f"{permission_data.resource.lower()}.{permission_data.action.lower()}"
    if permission_data.name.lower() != expected_name:
        raise WrextValidationException(
            message=f"Permission name must match format: {expected_name}",
            context={"provided": permission_data.name, "expected": expected_name}
        )

    # Create new permission
    new_permission = Permission(
        name=permission_data.name.lower(),  # Ensure lowercase
        display_name=permission_data.display_name,
        description=permission_data.description,
        resource=permission_data.resource.lower(),
        action=permission_data.action.lower()
    )

    db.add(new_permission)
    await db.flush()
    await db.refresh(new_permission)

    logger.info(f"Permission created: {new_permission.name} by user {user_id}")

    return {
        "data": {"permission": new_permission.to_dict()},
        "message": f"Permission '{new_permission.name}' created successfully",
        "status_code": status.HTTP_201_CREATED
    }


@router.put("/{permission_id}", response_model=dict)
@db_transaction_handler("update permission", auto_commit=True)
@require_permissions("permission.update", workspace_scoped=False)
async def update_permission(
    request: Request,
    permission_id: str,
    permission_data: PermissionUpdate,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Update an existing permission.

    Requires: permission.update permission OR admin role

    Parameters:
    - permission_id: UUID of the permission to update

    Request Body:
    - display_name: Optional new display name
    - description: Optional new description
    - resource: Optional new resource type
    - action: Optional new action type

    Note:
    - Cannot change permission name (immutable)

    Returns:
    - Updated permission details
    """
    # Check permission
    user_id = current_user.get("identity")
    await check_permission_access(db, user_id, "permission.update")

    # Get permission
    permission = await get_or_404(db, Permission, permission_id, "permission")

    # Update fields
    if permission_data.display_name is not None:
        permission.display_name = permission_data.display_name

    if permission_data.description is not None:
        permission.description = permission_data.description

    if permission_data.resource is not None:
        permission.resource = permission_data.resource.lower()

    if permission_data.action is not None:
        permission.action = permission_data.action.lower()

    # If resource or action changed, validate name still matches
    if permission_data.resource or permission_data.action:
        expected_name = f"{permission.resource}.{permission.action}"
        if permission.name != expected_name:
            # Update name to match new resource.action
            # Check if new name already exists
            result = await db.execute(
                select(Permission).where(
                    Permission.name == expected_name,
                    Permission.id != permission_id
                )
            )
            existing = result.scalar_one_or_none()

            if existing:
                raise DuplicateResourceException(
                    message=f"Permission '{expected_name}' already exists",
                    context={"name": expected_name}
                )

            permission.name = expected_name

    await db.flush()
    await db.refresh(permission)

    logger.info(f"Permission updated: {permission.name} by user {user_id}")

    return {
        "data": {"permission": permission.to_dict()},
        "message": f"Permission '{permission.name}' updated successfully"
    }


@router.delete("/{permission_id}", response_model=dict)
@db_transaction_handler("delete permission", auto_commit=True)
@require_permissions("permission.delete", workspace_scoped=False)
async def delete_permission(
    request: Request,
    permission_id: str,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Delete a permission.

    Requires: permission.delete permission OR admin role

    Parameters:
    - permission_id: UUID of the permission to delete

    Restrictions:
    - Cannot delete permissions assigned to roles

    Returns:
    - Success message
    """
    # Check permission
    user_id = current_user.get("identity")
    await check_permission_access(db, user_id, "permission.delete")

    # Get permission
    permission = await get_or_404(db, Permission, permission_id, "permission")

    # Check if permission is assigned to any roles
    result = await db.execute(
        select(RolePermission).where(
            RolePermission.permission_id == permission_id
        )
    )
    role_count = len(result.scalars().all())

    if role_count > 0:
        raise WrextValidationException(
            message=f"Cannot delete permission assigned to {role_count} role(s)",
            context={"permission_id": permission_id, "role_count": role_count}
        )

    # Delete the permission
    permission_name = permission.name
    await db.delete(permission)
    await db.flush()

    logger.info(f"Permission deleted: {permission_name} by user {user_id}")

    return {
        "data": {"permission_id": permission_id},
        "message": f"Permission '{permission_name}' deleted successfully"
    }
