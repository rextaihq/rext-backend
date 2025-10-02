"""
Role management API endpoints.

This module provides CRUD operations for roles with proper permission checks.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from datetime import datetime

from src.api.database.database import get_db
from src.api.security.auth import get_current_user
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
    PermissionSummary
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
def list_roles(
    request: Request,
    include_permissions: bool = Query(False, description="Include permissions for each role"),
    db: Session = Depends(get_db),
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
        is_user_admin = db.query(UserRole).join(Role).filter(
            UserRole.user_id == user_id,
            Role.name.in_(["admin", "super_admin"])
        ).first() is not None

        if not is_user_admin:
            # Check for role.read permission
            has_permission = (
                db.query(Permission.name)
                .join(RolePermission, RolePermission.permission_id == Permission.id)
                .join(UserRole, UserRole.role_id == RolePermission.role_id)
                .filter(
                    UserRole.user_id == user_id,
                    Permission.name == "role.read"
                )
                .first()
            )

            if not has_permission:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Insufficient permissions. Required: role.read or admin role"
                )

        # Query roles
        query = db.query(Role).order_by(Role.hierarchy_level.desc())
        roles = query.all()

        # Format response
        if include_permissions:
            roles_data = []
            for role in roles:
                # Get permissions for this role
                permissions = (
                    db.query(Permission)
                    .join(RolePermission, RolePermission.permission_id == Permission.id)
                    .filter(RolePermission.role_id == role.id)
                    .all()
                )

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
def get_role(
    request: Request,
    role_id: str,
    include_permissions: bool = Query(False, description="Include permissions"),
    db: Session = Depends(get_db),
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
        is_user_admin = db.query(UserRole).join(Role).filter(
            UserRole.user_id == user_id,
            Role.name.in_(["admin", "super_admin"])
        ).first() is not None

        if not is_user_admin:
            # Check for role.read permission
            has_permission = (
                db.query(Permission.name)
                .join(RolePermission, RolePermission.permission_id == Permission.id)
                .join(UserRole, UserRole.role_id == RolePermission.role_id)
                .filter(
                    UserRole.user_id == user_id,
                    Permission.name == "role.read"
                )
                .first()
            )

            if not has_permission:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Insufficient permissions. Required: role.read or admin role"
                )

        # Get role
        role = db.query(Role).filter(Role.id == role_id).first()

        if not role:
            raise ResourceNotFoundException(
                message="Role not found",
                context={"role_id": role_id}
            )

        role_data = role.to_dict()

        # Include permissions if requested
        if include_permissions:
            permissions = (
                db.query(Permission)
                .join(RolePermission, RolePermission.permission_id == Permission.id)
                .filter(RolePermission.role_id == role.id)
                .all()
            )

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
def create_role(
    request: Request,
    role_data: RoleCreate,
    db: Session = Depends(get_db),
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
        is_user_admin = db.query(UserRole).join(Role).filter(
            UserRole.user_id == user_id,
            Role.name.in_(["admin", "super_admin"])
        ).first() is not None

        if not is_user_admin:
            # Check for role.create permission
            has_permission = (
                db.query(Permission.name)
                .join(RolePermission, RolePermission.permission_id == Permission.id)
                .join(UserRole, UserRole.role_id == RolePermission.role_id)
                .filter(
                    UserRole.user_id == user_id,
                    Permission.name == "role.create"
                )
                .first()
            )

            if not has_permission:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Insufficient permissions. Required: role.create or admin role"
                )

        # Check if role name already exists (case-insensitive)
        existing_role = db.query(Role).filter(
            func.lower(Role.name) == role_data.name.lower()
        ).first()

        if existing_role:
            raise DuplicateResourceException(
                message="Role with this name already exists",
                context={"name": role_data.name}
            )

        # Check if display_name already exists
        existing_display = db.query(Role).filter(
            Role.display_name == role_data.display_name
        ).first()

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
        db.commit()
        db.refresh(new_role)

        logger.info(f"Role created: {new_role.name} by user {user_id}")

        return created(
            data={"role": new_role.to_dict()},
            request=request,
            message=f"Role '{new_role.display_name}' created successfully"
        )

    except (HTTPException, DuplicateResourceException):
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error creating role: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create role"
        )


@router.put("/{role_id}", response_model=dict)
def update_role(
    request: Request,
    role_id: str,
    role_data: RoleUpdate,
    db: Session = Depends(get_db),
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
        is_user_admin = db.query(UserRole).join(Role).filter(
            UserRole.user_id == user_id,
            Role.name.in_(["admin", "super_admin"])
        ).first() is not None

        if not is_user_admin:
            # Check for role.update permission
            has_permission = (
                db.query(Permission.name)
                .join(RolePermission, RolePermission.permission_id == Permission.id)
                .join(UserRole, UserRole.role_id == RolePermission.role_id)
                .filter(
                    UserRole.user_id == user_id,
                    Permission.name == "role.update"
                )
                .first()
            )

            if not has_permission:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Insufficient permissions. Required: role.update or admin role"
                )

        # Get role
        role = db.query(Role).filter(Role.id == role_id).first()

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
            existing_display = db.query(Role).filter(
                Role.display_name == role_data.display_name,
                Role.id != role_id
            ).first()

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

        db.commit()
        db.refresh(role)

        logger.info(f"Role updated: {role.name} by user {user_id}")

        return success(
            data={"role": role.to_dict()},
            request=request,
            message=f"Role '{role.display_name}' updated successfully"
        )

    except (HTTPException, ResourceNotFoundException, DuplicateResourceException):
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating role {role_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update role"
        )


@router.delete("/{role_id}", response_model=dict)
def delete_role(
    request: Request,
    role_id: str,
    db: Session = Depends(get_db),
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
        is_user_admin = db.query(UserRole).join(Role).filter(
            UserRole.user_id == user_id,
            Role.name.in_(["admin", "super_admin"])
        ).first() is not None

        if not is_user_admin:
            # Check for role.delete permission
            has_permission = (
                db.query(Permission.name)
                .join(RolePermission, RolePermission.permission_id == Permission.id)
                .join(UserRole, UserRole.role_id == RolePermission.role_id)
                .filter(
                    UserRole.user_id == user_id,
                    Permission.name == "role.delete"
                )
                .first()
            )

            if not has_permission:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Insufficient permissions. Required: role.delete or admin role"
                )

        # Get role
        role = db.query(Role).filter(Role.id == role_id).first()

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
        user_count = db.query(UserRole).filter(UserRole.role_id == role_id).count()

        if user_count > 0:
            raise WrextValidationException(
                message=f"Cannot delete role assigned to {user_count} user(s)",
                context={"role_id": role_id, "user_count": user_count}
            )

        # Delete role permissions first (cascade)
        db.query(RolePermission).filter(RolePermission.role_id == role_id).delete()

        # Delete the role
        role_name = role.display_name
        db.delete(role)
        db.commit()

        logger.info(f"Role deleted: {role.name} by user {user_id}")

        return success(
            data={"role_id": role_id},
            request=request,
            message=f"Role '{role_name}' deleted successfully"
        )

    except (HTTPException, ResourceNotFoundException, WrextValidationException):
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting role {role_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete role"
        )
