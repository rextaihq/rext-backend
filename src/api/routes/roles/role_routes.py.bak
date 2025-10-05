"""
Role management API endpoints.

This module provides CRUD operations for roles with proper permission checks.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select
from typing import List, Optional
from datetime import datetime

from src.api.database.async_database import get_async_db
from src.api.security.dependencies import get_current_user
from src.api.middleware.permissions import require_permissions, is_admin
from src.api.models.user_models.roles import Role
from src.api.models.user_models.role_permissions import RolePermission
from src.api.models.user_models.permissions import Permission
from src.api.models.user_models.user_roles import UserRole
from src.api.schema.role_schema import (
    RoleCreate,
    RoleUpdate,
    RoleResponse,
    RoleWithPermissions,
    PermissionSummary,
    AssignPermissionsRequest
)
from src.utils.response_utils import success, error, created
from src.api.middleware.exceptions import (
    DuplicateResourceException,
    WrextValidationException,
    ResourceNotFoundException
)
from src.utils.logger import logger


router = APIRouter(
    prefix="/roles",
    tags=["roles"]
)


@router.get("", response_model=dict)
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
    try:
        # Check permission (allow if user has role.read OR is admin)
        user_id = current_user.get("identity")

        # Check if admin
        result = await db.execute(
            select(UserRole).join(Role).where(
                UserRole.user_id == user_id,
                Role.name.in_(["admin", "super_admin"])
            )
        )
        is_user_admin = result.scalar_one_or_none() is not None

        if not is_user_admin:
            # Check for role.read permission
            result = await db.execute(
                select(Permission.name)
                .join(RolePermission, RolePermission.permission_id == Permission.id)
                .join(UserRole, UserRole.role_id == RolePermission.role_id)
                .where(
                    UserRole.user_id == user_id,
                    Permission.name == "role.read"
                )
            )
            has_permission = result.scalar_one_or_none()

            if not has_permission:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Insufficient permissions. Required: role.read or admin role"
                )

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

        return success(
            data={"roles": roles_data, "count": len(roles_data)},
            request=request,
            message=f"Retrieved {len(roles_data)} roles"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing roles: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve roles"
        )


@router.get("/{role_id}", response_model=dict)
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
    try:
        # Check permission (allow if user has role.read OR is admin)
        user_id = current_user.get("identity")

        # Check if admin
        result = await db.execute(
            select(UserRole).join(Role).where(
                UserRole.user_id == user_id,
                Role.name.in_(["admin", "super_admin"])
            )
        )
        is_user_admin = result.scalar_one_or_none() is not None

        if not is_user_admin:
            # Check for role.read permission
            result = await db.execute(
                select(Permission.name)
                .join(RolePermission, RolePermission.permission_id == Permission.id)
                .join(UserRole, UserRole.role_id == RolePermission.role_id)
                .where(
                    UserRole.user_id == user_id,
                    Permission.name == "role.read"
                )
            )
            has_permission = result.scalar_one_or_none()

            if not has_permission:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Insufficient permissions. Required: role.read or admin role"
                )

        # Get role
        result = await db.execute(select(Role).where(Role.id == role_id))
        role = result.scalar_one_or_none()

        if not role:
            raise ResourceNotFoundException(
                message="Role not found",
                context={"role_id": role_id}
            )

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

        return success(
            data={"role": role_data},
            request=request,
            message="Role retrieved successfully"
        )

    except (HTTPException, ResourceNotFoundException):
        raise
    except Exception as e:
        logger.error(f"Error getting role {role_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve role"
        )


@router.post("", response_model=dict, status_code=status.HTTP_201_CREATED)
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
    try:
        # Check permission (allow if user has role.create OR is admin)
        user_id = current_user.get("identity")

        # Check if admin
        result = await db.execute(
            select(UserRole).join(Role).where(
                UserRole.user_id == user_id,
                Role.name.in_(["admin", "super_admin"])
            )
        )
        is_user_admin = result.scalar_one_or_none() is not None

        if not is_user_admin:
            # Check for role.create permission
            result = await db.execute(
                select(Permission.name)
                .join(RolePermission, RolePermission.permission_id == Permission.id)
                .join(UserRole, UserRole.role_id == RolePermission.role_id)
                .where(
                    UserRole.user_id == user_id,
                    Permission.name == "role.create"
                )
            )
            has_permission = result.scalar_one_or_none()

            if not has_permission:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Insufficient permissions. Required: role.create or admin role"
                )

        # Check if role name already exists (case-insensitive)
        result = await db.execute(
            select(Role).where(
                func.lower(Role.name) == role_data.name.lower()
            )
        )
        existing_role = result.scalar_one_or_none()

        if existing_role:
            raise DuplicateResourceException(
                message="Role with this name already exists",
                context={"name": role_data.name}
            )

        # Check if display_name already exists
        result = await db.execute(
            select(Role).where(
                Role.display_name == role_data.display_name
            )
        )
        existing_display = result.scalar_one_or_none()

        if existing_display:
            raise DuplicateResourceException(
                message="Role with this display name already exists",
                context={"display_name": role_data.display_name}
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
        await db.commit()
        await db.refresh(new_role)

        logger.info(f"Role created: {new_role.name} by user {user_id}")

        return created(
            data={"role": new_role.to_dict()},
            request=request,
            message=f"Role '{new_role.display_name}' created successfully"
        )

    except (HTTPException, DuplicateResourceException):
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error creating role: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create role"
        )


@router.put("/{role_id}", response_model=dict)
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
    try:
        # Check permission (allow if user has role.update OR is admin)
        user_id = current_user.get("identity")

        # Check if admin
        result = await db.execute(
            select(UserRole).join(Role).where(
                UserRole.user_id == user_id,
                Role.name.in_(["admin", "super_admin"])
            )
        )
        is_user_admin = result.scalar_one_or_none() is not None

        if not is_user_admin:
            # Check for role.update permission
            result = await db.execute(
                select(Permission.name)
                .join(RolePermission, RolePermission.permission_id == Permission.id)
                .join(UserRole, UserRole.role_id == RolePermission.role_id)
                .where(
                    UserRole.user_id == user_id,
                    Permission.name == "role.update"
                )
            )
            has_permission = result.scalar_one_or_none()

            if not has_permission:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Insufficient permissions. Required: role.update or admin role"
                )

        # Get role
        result = await db.execute(select(Role).where(Role.id == role_id))
        role = result.scalar_one_or_none()

        if not role:
            raise ResourceNotFoundException(
                message="Role not found",
                context={"role_id": role_id}
            )

        # Check if system role
        if role.is_system_role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot update system roles"
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

        await db.commit()
        await db.refresh(role)

        logger.info(f"Role updated: {role.name} by user {user_id}")

        return success(
            data={"role": role.to_dict()},
            request=request,
            message=f"Role '{role.display_name}' updated successfully"
        )

    except (HTTPException, ResourceNotFoundException, DuplicateResourceException):
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error updating role {role_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update role"
        )


@router.delete("/{role_id}", response_model=dict)
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
    try:
        # Check permission (allow if user has role.delete OR is admin)
        user_id = current_user.get("identity")

        # Check if admin
        result = await db.execute(
            select(UserRole).join(Role).where(
                UserRole.user_id == user_id,
                Role.name.in_(["admin", "super_admin"])
            )
        )
        is_user_admin = result.scalar_one_or_none() is not None

        if not is_user_admin:
            # Check for role.delete permission
            result = await db.execute(
                select(Permission.name)
                .join(RolePermission, RolePermission.permission_id == Permission.id)
                .join(UserRole, UserRole.role_id == RolePermission.role_id)
                .where(
                    UserRole.user_id == user_id,
                    Permission.name == "role.delete"
                )
            )
            has_permission = result.scalar_one_or_none()

            if not has_permission:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Insufficient permissions. Required: role.delete or admin role"
                )

        # Get role
        result = await db.execute(select(Role).where(Role.id == role_id))
        role = result.scalar_one_or_none()

        if not role:
            raise ResourceNotFoundException(
                message="Role not found",
                context={"role_id": role_id}
            )

        # Check if system role
        if role.is_system_role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot delete system roles"
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
        await db.commit()

        logger.info(f"Role deleted: {role.name} by user {user_id}")

        return success(
            data={"role_id": role_id},
            request=request,
            message=f"Role '{role_name}' deleted successfully"
        )

    except (HTTPException, ResourceNotFoundException, WrextValidationException):
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error deleting role {role_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete role"
        )


# ============================================================================
# ROLE-PERMISSION ASSIGNMENT ENDPOINTS
# ============================================================================


@router.post("/{role_id}/permissions", response_model=dict)
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
    try:
        # Check permission (allow if user has role.manage_permissions OR is admin)
        user_id = current_user.get("identity")

        # Check if admin
        result = await db.execute(
            select(UserRole).join(Role).where(
                UserRole.user_id == user_id,
                Role.name.in_(["admin", "super_admin"])
            )
        )
        is_user_admin = result.scalar_one_or_none() is not None

        if not is_user_admin:
            # Check for role.manage_permissions permission
            result = await db.execute(
                select(Permission.name)
                .join(RolePermission, RolePermission.permission_id == Permission.id)
                .join(UserRole, UserRole.role_id == RolePermission.role_id)
                .where(
                    UserRole.user_id == user_id,
                    Permission.name == "role.manage_permissions"
                )
            )
            has_permission = result.scalar_one_or_none()

            if not has_permission:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Insufficient permissions. Required: role.manage_permissions or admin role"
                )

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

        await db.commit()

        logger.info(
            f"Added {added_count} permissions to role '{role.name}' "
            f"(skipped {skipped_count} existing, {invalid_count} invalid) "
            f"by user {user_id}"
        )

        return success(
            data={
                "role_id": str(role_id),
                "role_name": role.name,
                "added_count": added_count,
                "skipped_count": skipped_count,
                "invalid_count": invalid_count
            },
            request=request,
            message=f"Added {added_count} permission(s) to role '{role.display_name}'"
        )

    except (HTTPException, ResourceNotFoundException):
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error assigning permissions to role {role_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to assign permissions"
        )


@router.delete("/{role_id}/permissions/{permission_id}", response_model=dict)
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
    try:
        # Check permission (allow if user has role.manage_permissions OR is admin)
        user_id = current_user.get("identity")

        # Check if admin
        result = await db.execute(
            select(UserRole).join(Role).where(
                UserRole.user_id == user_id,
                Role.name.in_(["admin", "super_admin"])
            )
        )
        is_user_admin = result.scalar_one_or_none() is not None

        if not is_user_admin:
            # Check for role.manage_permissions permission
            result = await db.execute(
                select(Permission.name)
                .join(RolePermission, RolePermission.permission_id == Permission.id)
                .join(UserRole, UserRole.role_id == RolePermission.role_id)
                .where(
                    UserRole.user_id == user_id,
                    Permission.name == "role.manage_permissions"
                )
            )
            has_permission = result.scalar_one_or_none()

            if not has_permission:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Insufficient permissions. Required: role.manage_permissions or admin role"
                )

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
        await db.commit()

        logger.info(
            f"Revoked permission '{permission.name if permission else permission_id}' "
            f"from role '{role.name if role else role_id}' by user {user_id}"
        )

        return success(
            data={
                "role_id": str(role_id),
                "permission_id": str(permission_id),
                "role_name": role.name if role else None,
                "permission_name": permission.name if permission else None
            },
            request=request,
            message=f"Permission revoked from role"
        )

    except (HTTPException, ResourceNotFoundException):
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Error revoking permission {permission_id} from role {role_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to revoke permission"
        )
