"""
Permission management API endpoints.

This module provides CRUD operations for permissions with proper authorization.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from datetime import datetime

from src.api.database.database import get_db
from src.api.security.auth import get_current_user
from src.api.middleware.permissions import require_permissions, is_admin
from src.api.models.user_models.permissions import Permission
from src.api.models.user_models.role_permissions import RolePermission
from src.api.models.user_models.roles import Role
from src.api.models.user_models.user_roles import UserRole
from src.api.schema.permission_schema import (
    PermissionCreate,
    PermissionUpdate,
    PermissionResponse,
    PermissionWithRoles,
    RoleSummary
)
from src.utils.response_utils import success, error, created
from src.api.middleware.exceptions import (
    DuplicateResourceException,
    WrextValidationException,
    ResourceNotFoundException
)
from src.utils.logger import logger


router = APIRouter(
    prefix="/permissions",
    tags=["permissions"]
)


@router.get("", response_model=dict)
def list_permissions(
    request: Request,
    resource: Optional[str] = Query(None, description="Filter by resource type"),
    include_roles: bool = Query(False, description="Include roles for each permission"),
    db: Session = Depends(get_db),
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
    try:
        # Check permission (allow if user has permission.read OR is admin)
        user_id = current_user.get("identity")

        # Check if admin
        is_user_admin = db.query(UserRole).join(Role).filter(
            UserRole.user_id == user_id,
            Role.name.in_(["admin", "super_admin"])
        ).first() is not None

        if not is_user_admin:
            # Check for permission.read permission
            has_permission = (
                db.query(Permission.name)
                .join(RolePermission, RolePermission.permission_id == Permission.id)
                .join(UserRole, UserRole.role_id == RolePermission.role_id)
                .filter(
                    UserRole.user_id == user_id,
                    Permission.name == "permission.read"
                )
                .first()
            )

            if not has_permission:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Insufficient permissions. Required: permission.read or admin role"
                )

        # Query permissions
        query = db.query(Permission)

        # Filter by resource if provided
        if resource:
            query = query.filter(Permission.resource == resource)

        permissions = query.order_by(Permission.resource, Permission.action).all()

        # Format response
        if include_roles:
            permissions_data = []
            for perm in permissions:
                # Get roles that have this permission
                roles = (
                    db.query(Role)
                    .join(RolePermission, RolePermission.role_id == Role.id)
                    .filter(RolePermission.permission_id == perm.id)
                    .all()
                )

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

        return success(
            data={"permissions": permissions_data, "count": len(permissions_data)},
            request=request,
            message=f"Retrieved {len(permissions_data)} permissions"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing permissions: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve permissions"
        )


@router.get("/{permission_id}", response_model=dict)
def get_permission(
    request: Request,
    permission_id: str,
    include_roles: bool = Query(False, description="Include roles"),
    db: Session = Depends(get_db),
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
    try:
        # Check permission (allow if user has permission.read OR is admin)
        user_id = current_user.get("identity")

        # Check if admin
        is_user_admin = db.query(UserRole).join(Role).filter(
            UserRole.user_id == user_id,
            Role.name.in_(["admin", "super_admin"])
        ).first() is not None

        if not is_user_admin:
            # Check for permission.read permission
            has_permission = (
                db.query(Permission.name)
                .join(RolePermission, RolePermission.permission_id == Permission.id)
                .join(UserRole, UserRole.role_id == RolePermission.role_id)
                .filter(
                    UserRole.user_id == user_id,
                    Permission.name == "permission.read"
                )
                .first()
            )

            if not has_permission:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Insufficient permissions. Required: permission.read or admin role"
                )

        # Get permission
        permission = db.query(Permission).filter(Permission.id == permission_id).first()

        if not permission:
            raise ResourceNotFoundException(
                message="Permission not found",
                context={"permission_id": permission_id}
            )

        perm_data = permission.to_dict()

        # Include roles if requested
        if include_roles:
            roles = (
                db.query(Role)
                .join(RolePermission, RolePermission.role_id == Role.id)
                .filter(RolePermission.permission_id == permission.id)
                .all()
            )

            perm_data["roles"] = [
                {
                    "id": str(role.id),
                    "name": role.name,
                    "display_name": role.display_name,
                    "hierarchy_level": role.hierarchy_level
                }
                for role in roles
            ]

        return success(
            data={"permission": perm_data},
            request=request,
            message="Permission retrieved successfully"
        )

    except (HTTPException, ResourceNotFoundException):
        raise
    except Exception as e:
        logger.error(f"Error getting permission {permission_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve permission"
        )


@router.post("", response_model=dict, status_code=status.HTTP_201_CREATED)
def create_permission(
    request: Request,
    permission_data: PermissionCreate,
    db: Session = Depends(get_db),
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
    try:
        # Check permission (allow if user has permission.create OR is admin)
        user_id = current_user.get("identity")

        # Check if admin
        is_user_admin = db.query(UserRole).join(Role).filter(
            UserRole.user_id == user_id,
            Role.name.in_(["admin", "super_admin"])
        ).first() is not None

        if not is_user_admin:
            # Check for permission.create permission
            has_permission = (
                db.query(Permission.name)
                .join(RolePermission, RolePermission.permission_id == Permission.id)
                .join(UserRole, UserRole.role_id == RolePermission.role_id)
                .filter(
                    UserRole.user_id == user_id,
                    Permission.name == "permission.create"
                )
                .first()
            )

            if not has_permission:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Insufficient permissions. Required: permission.create or admin role"
                )

        # Check if permission name already exists (case-insensitive)
        existing_perm = db.query(Permission).filter(
            func.lower(Permission.name) == permission_data.name.lower()
        ).first()

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
        db.commit()
        db.refresh(new_permission)

        logger.info(f"Permission created: {new_permission.name} by user {user_id}")

        return created(
            data={"permission": new_permission.to_dict()},
            request=request,
            message=f"Permission '{new_permission.name}' created successfully"
        )

    except (HTTPException, DuplicateResourceException, WrextValidationException):
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error creating permission: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create permission"
        )


@router.put("/{permission_id}", response_model=dict)
def update_permission(
    request: Request,
    permission_id: str,
    permission_data: PermissionUpdate,
    db: Session = Depends(get_db),
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
    try:
        # Check permission (allow if user has permission.update OR is admin)
        user_id = current_user.get("identity")

        # Check if admin
        is_user_admin = db.query(UserRole).join(Role).filter(
            UserRole.user_id == user_id,
            Role.name.in_(["admin", "super_admin"])
        ).first() is not None

        if not is_user_admin:
            # Check for permission.update permission
            has_permission = (
                db.query(Permission.name)
                .join(RolePermission, RolePermission.permission_id == Permission.id)
                .join(UserRole, UserRole.role_id == RolePermission.role_id)
                .filter(
                    UserRole.user_id == user_id,
                    Permission.name == "permission.update"
                )
                .first()
            )

            if not has_permission:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Insufficient permissions. Required: permission.update or admin role"
                )

        # Get permission
        permission = db.query(Permission).filter(Permission.id == permission_id).first()

        if not permission:
            raise ResourceNotFoundException(
                message="Permission not found",
                context={"permission_id": permission_id}
            )

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
                existing = db.query(Permission).filter(
                    Permission.name == expected_name,
                    Permission.id != permission_id
                ).first()

                if existing:
                    raise DuplicateResourceException(
                        message=f"Permission '{expected_name}' already exists",
                        context={"name": expected_name}
                    )

                permission.name = expected_name

        db.commit()
        db.refresh(permission)

        logger.info(f"Permission updated: {permission.name} by user {user_id}")

        return success(
            data={"permission": permission.to_dict()},
            request=request,
            message=f"Permission '{permission.name}' updated successfully"
        )

    except (HTTPException, ResourceNotFoundException, DuplicateResourceException):
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating permission {permission_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update permission"
        )


@router.delete("/{permission_id}", response_model=dict)
def delete_permission(
    request: Request,
    permission_id: str,
    db: Session = Depends(get_db),
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
    try:
        # Check permission (allow if user has permission.delete OR is admin)
        user_id = current_user.get("identity")

        # Check if admin
        is_user_admin = db.query(UserRole).join(Role).filter(
            UserRole.user_id == user_id,
            Role.name.in_(["admin", "super_admin"])
        ).first() is not None

        if not is_user_admin:
            # Check for permission.delete permission
            has_permission = (
                db.query(Permission.name)
                .join(RolePermission, RolePermission.permission_id == Permission.id)
                .join(UserRole, UserRole.role_id == RolePermission.role_id)
                .filter(
                    UserRole.user_id == user_id,
                    Permission.name == "permission.delete"
                )
                .first()
            )

            if not has_permission:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Insufficient permissions. Required: permission.delete or admin role"
                )

        # Get permission
        permission = db.query(Permission).filter(Permission.id == permission_id).first()

        if not permission:
            raise ResourceNotFoundException(
                message="Permission not found",
                context={"permission_id": permission_id}
            )

        # Check if permission is assigned to any roles
        role_count = db.query(RolePermission).filter(
            RolePermission.permission_id == permission_id
        ).count()

        if role_count > 0:
            raise WrextValidationException(
                message=f"Cannot delete permission assigned to {role_count} role(s)",
                context={"permission_id": permission_id, "role_count": role_count}
            )

        # Delete the permission
        permission_name = permission.name
        db.delete(permission)
        db.commit()

        logger.info(f"Permission deleted: {permission_name} by user {user_id}")

        return success(
            data={"permission_id": permission_id},
            request=request,
            message=f"Permission '{permission_name}' deleted successfully"
        )

    except (HTTPException, ResourceNotFoundException, WrextValidationException):
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting permission {permission_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete permission"
        )
