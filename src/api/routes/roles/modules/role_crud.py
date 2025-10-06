"""
Role CRUD operations module.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select
from datetime import datetime

from src.api.database.async_database import get_async_db
from src.api.security.dependencies import get_current_user
from src.api.models.user_models.roles import Role
from src.api.models.user_models.role_permissions import RolePermission
from src.api.models.user_models.permissions import Permission
from src.api.models.user_models.user_roles import UserRole
from src.api.schema.role_schema import (
    RoleCreate,
    RoleUpdate,
)
from src.utils.response_utils import success, error, created
from src.utils.db_utils import get_or_404, ensure_unique
from src.utils.route_decorators import db_transaction_handler, require_permissions
from src.api.middleware.exceptions import (
    DuplicateResourceException,
    WrextValidationException,
    ResourceNotFoundException,
    WrextAPIException
)
from src.utils.logger import logger
from .helpers import check_role_permission


router = APIRouter()


@router.get("/", response_model=dict)
@db_transaction_handler("list roles", auto_commit=False)
async def list_roles(
    request: Request,
    include_permissions: bool = Query(False, description="Include permissions for each role"),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    List all roles.

    Requires: role.read permission OR admin role

    Query Parameters:
    - include_permissions: If true, include permissions for each role

    Returns:
    - List of roles sorted by hierarchy_level (descending)
    """
    # Check permission
    user_id = current_user.get("identity")
    await check_role_permission(db, user_id, "role.read")

    # Query roles
    result = await db.execute(select(Role).order_by(Role.hierarchy_level.desc()))
    roles = result.scalars().all()

    # Format response
    if include_permissions:
        roles_data = []
        for role in roles:
            # Get permissions for this role
            result = await db.execute(
                select(Permission)
                .join(RolePermission, RolePermission.permission_id == Permission.id)
                .where(RolePermission.role_id == role.id)
            )
            permissions = result.scalars().all()

            role_dict = role.to_dict()
            role_dict["permissions"] = [
                {
                    "id": str(perm.id),
                    "name": perm.name,
                    "display_name": perm.display_name,
                    "resource": perm.resource,
                    "action": perm.action
                }
                for perm in permissions
            ]
            roles_data.append(role_dict)
    else:
        roles_data = [role.to_dict() for role in roles]

    return {
        "data": {"roles": roles_data, "count": len(roles_data)},
        "message": f"Retrieved {len(roles_data)} roles"
    }


@router.get("/{role_id}", response_model=dict)
@db_transaction_handler("get role", auto_commit=False)
async def get_role(
    request: Request,
    role_id: str,
    include_permissions: bool = Query(False, description="Include permissions"),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get a specific role by ID.

    Requires: role.read permission OR admin role

    Parameters:
    - role_id: UUID of the role

    Query Parameters:
    - include_permissions: If true, include permissions

    Returns:
    - Role details with optional permissions
    """
    # Check permission
    user_id = current_user.get("identity")
    await check_role_permission(db, user_id, "role.read")

    # Get role
    role = await get_or_404(db, Role, role_id, "role")

    role_data = role.to_dict()

    # Include permissions if requested
    if include_permissions:
        result = await db.execute(
            select(Permission)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .where(RolePermission.role_id == role.id)
        )
        permissions = result.scalars().all()

        role_data["permissions"] = [
            {
                "id": str(perm.id),
                "name": perm.name,
                "display_name": perm.display_name,
                "resource": perm.resource,
                "action": perm.action
            }
            for perm in permissions
        ]

    return {
        "data": {"role": role_data},
        "message": "Role retrieved successfully"
    }


@router.post("/", response_model=dict, status_code=status.HTTP_201_CREATED)
@db_transaction_handler("create role", auto_commit=True)
@require_permissions("role.create", workspace_scoped=False)
async def create_role(
    request: Request,
    role_data: RoleCreate,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Create a new role.

    Requires: role.create permission OR admin role

    Request Body:
    - name: Unique role name (lowercase, no spaces)
    - display_name: Human-readable name
    - description: Optional description
    - hierarchy_level: 0-100 (default: 1)
    - is_system_role: Boolean (default: false)

    Returns:
    - Created role details
    """
    # Check permission
    user_id = current_user.get("identity")
    await check_role_permission(db, user_id, "role.create")

    # Check uniqueness (using db_utils)
    await ensure_unique(
        db, Role, "name", role_data.name.lower(),
        resource_type="role",
        error_message="Role with this name already exists"
    )

    await ensure_unique(
        db, Role, "display_name", role_data.display_name,
        resource_type="role",
        error_message="Role with this display name already exists"
    )

    # Create new role
    new_role = Role(
        name=role_data.name.lower(),  # Ensure lowercase
        display_name=role_data.display_name,
        description=role_data.description,
        hierarchy_level=role_data.hierarchy_level,
        is_system_role=role_data.is_system_role
    )

    db.add(new_role)
    await db.flush()
    await db.refresh(new_role)

    logger.info(f"Role created: {new_role.name} by user {user_id}")

    return {
        "data": {"role": new_role.to_dict()},
        "message": f"Role '{new_role.display_name}' created successfully"
    }


@router.put("/{role_id}", response_model=dict)
@db_transaction_handler("update role", auto_commit=True)
@require_permissions("role.update", workspace_scoped=False)
async def update_role(
    request: Request,
    role_id: str,
    role_data: RoleUpdate,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Update an existing role.

    Requires: role.update permission OR admin role

    Parameters:
    - role_id: UUID of the role to update

    Request Body:
    - display_name: Optional new display name
    - description: Optional new description
    - hierarchy_level: Optional new hierarchy level (0-100)

    Note:
    - Cannot update system roles (is_system_role=true)
    - Cannot change role name (immutable)

    Returns:
    - Updated role details
    """
    # Check permission
    user_id = current_user.get("identity")
    await check_role_permission(db, user_id, "role.update")

    # Get role
    role = await get_or_404(db, Role, role_id, "role")

    # Check if system role
    if role.is_system_role:
        raise WrextAPIException(
            status_code=status.HTTP_403_FORBIDDEN,
            message="Cannot update system roles"
        )

    # Check if display_name already exists (if being updated)
    if role_data.display_name and role_data.display_name != role.display_name:
        result = await db.execute(
            select(Role).where(
                Role.display_name == role_data.display_name,
                Role.id != role_id
            )
        )
        existing_display = result.scalar_one_or_none()

        if existing_display:
            raise DuplicateResourceException(
                message="Role with this display name already exists",
                context={"display_name": role_data.display_name}
            )

    # Update fields
    if role_data.display_name is not None:
        role.display_name = role_data.display_name

    if role_data.description is not None:
        role.description = role_data.description

    if role_data.hierarchy_level is not None:
        role.hierarchy_level = role_data.hierarchy_level

    role.updated_at = datetime.utcnow()

    await db.flush()
    await db.refresh(role)

    logger.info(f"Role updated: {role.name} by user {user_id}")

    return {
        "data": {"role": role.to_dict()},
        "message": f"Role '{role.display_name}' updated successfully"
    }


@router.delete("/{role_id}", response_model=dict)
@db_transaction_handler("delete role", auto_commit=True)
@require_permissions("role.delete", workspace_scoped=False)
async def delete_role(
    request: Request,
    role_id: str,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Delete a role.

    Requires: role.delete permission OR admin role

    Parameters:
    - role_id: UUID of the role to delete

    Restrictions:
    - Cannot delete system roles (is_system_role=true)
    - Cannot delete roles assigned to users

    Returns:
    - Success message
    """
    # Check permission
    user_id = current_user.get("identity")
    await check_role_permission(db, user_id, "role.delete")

    # Get role
    role = await get_or_404(db, Role, role_id, "role")

    # Check if system role
    if role.is_system_role:
        raise WrextAPIException(
            status_code=status.HTTP_403_FORBIDDEN,
            message="Cannot delete system roles"
        )

    # Check if role is assigned to any users
    result = await db.execute(select(UserRole).where(UserRole.role_id == role_id))
    user_count = len(result.scalars().all())

    if user_count > 0:
        raise WrextValidationException(
            message=f"Cannot delete role assigned to {user_count} user(s)",
            context={"role_id": role_id, "user_count": user_count}
        )

    # Delete role permissions first (cascade)
    result = await db.execute(select(RolePermission).where(RolePermission.role_id == role_id))
    role_permissions = result.scalars().all()
    for rp in role_permissions:
        await db.delete(rp)

    # Delete the role
    role_name = role.display_name
    await db.delete(role)

    logger.info(f"Role deleted: {role.name} by user {user_id}")

    return {
        "data": {"role_id": role_id},
        "message": f"Role '{role_name}' deleted successfully"
    }
