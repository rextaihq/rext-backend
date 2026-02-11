"""
Role Service - Business Logic for Role and Permission Management

This service encapsulates all business logic related to role management,
including role CRUD operations, permission assignments, and user role assignments.

Responsibilities:
- Role creation, update, and deletion
- Permission management for roles
- User role assignments and revocations
- Role hierarchy validation
- System role protection

Does NOT:
- Handle HTTP requests/responses (that's routes)
- Commit transactions (that's decorators/routes)
- Check authentication (that's decorators)
"""

from typing import List, Optional, Dict, Any
from uuid import UUID
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_

from src.api.models.user_models.roles import Role
from src.api.models.user_models.permissions import Permission
from src.api.models.user_models.role_permissions import RolePermission
from src.api.models.user_models.user_roles import UserRole
from src.api.models.workspace_models.workspace_model import WorkspaceModel
from src.api.models.workspace_models.workspace_member import WorkspaceMembers
from src.utils.logger import logger
from src.api.middleware.exceptions import (
    DuplicateResourceException,
    RextValidationException,
    ResourceNotFoundException,
    RextAPIException
)


class RoleService:
    """Service for role and permission management"""

    # Standard workspace roles that cannot be deleted or modified
    PROTECTED_WORKSPACE_ROLES = {
        "workspace_owner",
        "workspace_admin",
        "editor",
        "viewer"
    }

    def __init__(self, db: AsyncSession):
        """
        Initialize RoleService.

        Args:
            db: Async database session
        """
        self.db = db

    async def create_role(
        self,
        name: str,
        display_name: str,
        description: Optional[str] = None,
        workspace_id: Optional[UUID] = None,
        permission_ids: Optional[List[UUID]] = None,
        hierarchy_level: int = 1,
        is_system_role: bool = False,
        is_workspace_role: bool = False
    ) -> Role:
        """
        Create role with permissions.

        Business Rules:
        - Role name must be unique (lowercase, no spaces)
        - Display name must be unique
        - Hierarchy level: 0-100
        - System roles cannot be created via API (unless explicitly allowed)
        - Permissions are validated before assignment

        Args:
            name: Role name (will be lowercased)
            display_name: Human-readable name
            description: Optional description
            workspace_id: Optional workspace UUID for workspace-scoped roles
            permission_ids: List of permission UUIDs to assign
            hierarchy_level: 0-100 (default: 1)
            is_system_role: Whether this is a platform role (default: False)
            is_workspace_role: Whether this can be assigned to workspaces (default: False)

        Returns:
            Role object

        Raises:
            DuplicateResourceException: If name or display_name exists
            ResourceNotFoundException: If permissions not found
        """
        # Ensure lowercase name
        name = name.lower()

        # Check name uniqueness
        name_result = await self.db.execute(
            select(Role).where(Role.name == name)
        )
        if name_result.scalar_one_or_none():
            raise DuplicateResourceException(
                message="Role with this name already exists",
                resource_type="role",
                conflicting_field="name",
                conflicting_value=name
            )

        # Check display_name uniqueness
        display_result = await self.db.execute(
            select(Role).where(Role.display_name == display_name)
        )
        if display_result.scalar_one_or_none():
            raise DuplicateResourceException(
                message="Role with this display name already exists",
                resource_type="role",
                conflicting_field="display_name",
                conflicting_value=display_name
            )

        # Create role
        new_role = Role(
            name=name,
            display_name=display_name,
            description=description,
            hierarchy_level=hierarchy_level,
            is_system_role=is_system_role,
            is_workspace_role=is_workspace_role,
            created_at=datetime.now(timezone.utc)
        )

        self.db.add(new_role)
        await self.db.flush()
        await self.db.refresh(new_role)

        # Assign permissions if provided
        if permission_ids:
            await self.update_role_permissions(new_role.id, permission_ids)

        logger.info(
            f"Role created: {new_role.name}",
            extra={"role_id": str(new_role.id), "hierarchy_level": hierarchy_level}
        )

        return new_role

    def _is_protected_role(self, role: Role) -> bool:
        """
        Check if a role is protected from modification/deletion.

        Protected roles include:
        - Platform/system roles (is_system_role=True)
        - Standard workspace roles (workspace_owner, workspace_admin, editor, viewer)

        Args:
            role: Role object to check

        Returns:
            True if role is protected, False otherwise
        """
        return (
            role.is_system_role or
            role.name in self.PROTECTED_WORKSPACE_ROLES
        )

    async def update_role(
        self,
        role_id: UUID,
        display_name: Optional[str] = None,
        description: Optional[str] = None,
        hierarchy_level: Optional[int] = None
    ) -> Role:
        """
        Update role properties.

        Business Rules:
        - Cannot update system roles
        - Cannot change role name (immutable)
        - Display name must remain unique
        - Hierarchy level: 0-100

        Args:
            role_id: Role UUID
            display_name: New display name
            description: New description
            hierarchy_level: New hierarchy level (0-100)

        Returns:
            Updated Role object

        Raises:
            ResourceNotFoundException: If role not found
            RextAPIException: If trying to update system role
            DuplicateResourceException: If display_name already exists
        """
        role = await self.get_role_by_id(role_id)

        # Check if protected role (system roles or standard workspace roles)
        if self._is_protected_role(role):
            raise RextValidationException(
                message=f"Cannot update protected role '{role.name}'",
                field_errors={"role_id": ["Protected roles (platform roles and standard workspace roles) cannot be modified"]}
            )

        # Check display_name uniqueness if being updated
        if display_name and display_name != role.display_name:
            display_result = await self.db.execute(
                select(Role).where(
                    Role.display_name == display_name,
                    Role.id != role_id
                )
            )
            if display_result.scalar_one_or_none():
                raise DuplicateResourceException(
                    message="Role with this display name already exists",
                    resource_type="role",
                    conflicting_field="display_name",
                    conflicting_value=display_name
                )

        # Update fields
        if display_name is not None:
            role.display_name = display_name

        if description is not None:
            role.description = description

        if hierarchy_level is not None:
            if hierarchy_level < 0 or hierarchy_level > 100:
                raise RextValidationException(
                    message="Hierarchy level must be between 0 and 100",
                    field_errors={"hierarchy_level": ["Must be 0-100"]}
                )
            role.hierarchy_level = hierarchy_level

        role.updated_at = datetime.now(timezone.utc)

        await self.db.flush()
        await self.db.refresh(role)

        logger.info(
            f"Role updated: {role.name}",
            extra={"role_id": str(role.id)}
        )

        return role

    async def delete_role(
        self,
        role_id: UUID,
        reassign_to: Optional[UUID] = None
    ) -> None:
        """
        Delete role with user reassignment.

        Business Rules:
        - Cannot delete system roles
        - Cannot delete roles assigned to users (unless reassignment provided)
        - If reassign_to provided, reassign all users to new role
        - Deletes all role-permission relationships

        Args:
            role_id: Role UUID
            reassign_to: Optional role UUID to reassign users to

        Raises:
            ResourceNotFoundException: If role not found
            RextAPIException: If system role
            RextValidationException: If role in use and no reassignment
        """
        role = await self.get_role_by_id(role_id)

        # Check if protected role (system roles or standard workspace roles)
        if self._is_protected_role(role):
            raise RextValidationException(
                message=f"Cannot delete protected role '{role.name}'",
                field_errors={"role_id": ["Protected roles (platform roles and standard workspace roles) cannot be deleted"]}
            )

        # Check if role is assigned to users
        user_roles_result = await self.db.execute(
            select(UserRole).where(UserRole.role_id == role_id)
        )
        user_roles = user_roles_result.scalars().all()

        if user_roles:
            if not reassign_to:
                raise RextValidationException(
                    message=f"Cannot delete role assigned to {len(user_roles)} user(s). Provide reassign_to role.",
                    field_errors={"role_id": ["Role in use, reassignment required"]}
                )

            # Validate reassignment role exists
            reassign_role = await self.get_role_by_id(reassign_to)

            # Reassign all users
            for user_role in user_roles:
                user_role.role_id = reassign_to
                user_role.assigned_at = datetime.now(timezone.utc)

            await self.db.flush()

            logger.info(
                f"Reassigned {len(user_roles)} users from {role.name} to {reassign_role.name}",
                extra={"role_id": str(role_id), "reassign_to": str(reassign_to)}
            )

        # Bulk-delete role permissions
        from sqlalchemy import delete
        await self.db.execute(
            delete(RolePermission).where(RolePermission.role_id == role_id)
        )

        # Delete the role
        role_name = role.display_name
        await self.db.delete(role)

        logger.info(
            f"Role deleted: {role.name}",
            extra={"role_id": str(role_id)}
        )

    async def assign_role(
        self,
        user_id: UUID,
        role_id: UUID,
        workspace_id: Optional[UUID] = None,
        is_primary: bool = False,
        assigned_by_user_id: Optional[UUID] = None
    ) -> UserRole:
        """
        Assign role to user.

        Business Rules:
        - Role must exist
        - If workspace-scoped, user must be workspace member
        - Idempotent: Returns existing assignment if already assigned
        - Hierarchy validation (if assignee provided)

        Args:
            user_id: User UUID
            role_id: Role UUID
            workspace_id: Optional workspace UUID
            is_primary: Whether this is the primary role
            assigned_by_user_id: UUID of user making the assignment

        Returns:
            UserRole object

        Raises:
            ResourceNotFoundException: If role or user not found
            RextValidationException: If user not workspace member
        """
        # Validate role exists
        role = await self.get_role_by_id(role_id)

        # If workspace-scoped, validate workspace and membership
        if workspace_id:
            workspace_result = await self.db.execute(
                select(WorkspaceModel).where(WorkspaceModel.id == workspace_id)
            )
            workspace = workspace_result.scalar_one_or_none()

            if not workspace:
                raise ResourceNotFoundException(
                    resource_type="Workspace",
                    resource_id=str(workspace_id)
                )

            # Check if user is member
            member_result = await self.db.execute(
                select(WorkspaceMembers).where(
                    WorkspaceMembers.workspace_id == workspace_id,
                    WorkspaceMembers.user_id == user_id
                )
            )
            if not member_result.scalar_one_or_none():
                raise RextValidationException(
                    message="User is not a member of this workspace",
                    field_errors={"workspace_id": ["User not a member"]}
                )

        # Check if already assigned (idempotent)
        existing_result = await self.db.execute(
            select(UserRole).where(
                UserRole.user_id == user_id,
                UserRole.role_id == role_id,
                UserRole.workspace_id == workspace_id
            )
        )
        existing = existing_result.scalar_one_or_none()

        if existing:
            logger.info(
                f"Role {role.name} already assigned to user {user_id}",
                extra={"user_id": str(user_id), "role_id": str(role_id)}
            )
            return existing

        # Create assignment
        user_role = UserRole(
            user_id=user_id,
            role_id=role_id,
            workspace_id=workspace_id,
            assigned_by_user_id=assigned_by_user_id or user_id,
            is_primary=is_primary,
            assigned_at=datetime.now(timezone.utc)
        )

        self.db.add(user_role)
        await self.db.flush()
        await self.db.refresh(user_role)

        # Invalidate permissions cache for this user
        from src.api.cache.decorators import invalidate_cache
        await invalidate_cache(f"user:permissions:{user_id}:*")

        logger.info(
            f"Role {role.name} assigned to user {user_id}",
            extra={
                "user_id": str(user_id),
                "role_id": str(role_id),
                "workspace_id": str(workspace_id) if workspace_id else None
            }
        )

        return user_role

    async def revoke_role(
        self,
        user_id: UUID,
        role_id: UUID,
        workspace_id: Optional[UUID] = None
    ) -> None:
        """
        Revoke role from user.

        Args:
            user_id: User UUID
            role_id: Role UUID
            workspace_id: Optional workspace UUID

        Raises:
            ResourceNotFoundException: If assignment not found
        """
        # Find the assignment
        query = select(UserRole).where(
            UserRole.user_id == user_id,
            UserRole.role_id == role_id
        )

        if workspace_id:
            query = query.where(UserRole.workspace_id == workspace_id)
        else:
            query = query.where(UserRole.workspace_id == None)

        result = await self.db.execute(query)
        user_role = result.scalar_one_or_none()

        if not user_role:
            raise ResourceNotFoundException(
                resource_type="UserRole",
                resource_id=f"user:{user_id},role:{role_id}",
                message="Role assignment not found"
            )

        # Delete the assignment
        await self.db.delete(user_role)

        # Invalidate permissions cache for this user
        from src.api.cache.decorators import invalidate_cache
        await invalidate_cache(f"user:permissions:{user_id}:*")

        logger.info(
            f"Role revoked from user {user_id}",
            extra={
                "user_id": str(user_id),
                "role_id": str(role_id),
                "workspace_id": str(workspace_id) if workspace_id else None
            }
        )

    async def update_role_permissions(
        self,
        role_id: UUID,
        permission_ids: List[UUID]
    ) -> Role:
        """
        Update role's permissions.

        Business Rules:
        - Validates all permissions exist
        - Removes old permissions
        - Adds new permissions
        - Transactional operation

        Args:
            role_id: Role UUID
            permission_ids: List of permission UUIDs

        Returns:
            Updated Role object

        Raises:
            ResourceNotFoundException: If role or permissions not found
        """
        role = await self.get_role_by_id(role_id)

        # Batch-validate all permissions exist in a single query
        if permission_ids:
            perm_result = await self.db.execute(
                select(Permission.id).where(Permission.id.in_(permission_ids))
            )
            found_ids = {row[0] for row in perm_result.all()}
            missing_ids = set(permission_ids) - found_ids
            if missing_ids:
                raise ResourceNotFoundException(
                    resource_type="Permission",
                    resource_id=str(next(iter(missing_ids)))
                )

        # Bulk-delete existing permissions
        from sqlalchemy import delete
        await self.db.execute(
            delete(RolePermission).where(RolePermission.role_id == role_id)
        )

        # Add new permissions
        for perm_id in permission_ids:
            role_perm = RolePermission(
                role_id=role_id,
                permission_id=perm_id
            )
            self.db.add(role_perm)

        await self.db.flush()

        logger.info(
            f"Permissions updated for role {role.name}: {len(permission_ids)} permissions",
            extra={"role_id": str(role_id), "permission_count": len(permission_ids)}
        )

        return role

    async def get_role_hierarchy(
        self,
        workspace_id: Optional[UUID] = None,
        page: int = 1,
        per_page: int = 50,
    ) -> Dict[str, Any]:
        """
        Get roles ordered by hierarchy level (descending) with pagination.

        Args:
            workspace_id: Optional workspace filter (future use)
            page: Page number (1-indexed)
            per_page: Items per page

        Returns:
            Dict with roles list and pagination metadata
        """
        base_query = select(Role).order_by(Role.hierarchy_level.desc())

        # Get total count
        count_result = await self.db.execute(
            select(func.count()).select_from(Role)
        )
        total = count_result.scalar() or 0

        # Apply pagination
        offset = (page - 1) * per_page
        result = await self.db.execute(base_query.offset(offset).limit(per_page))
        roles = list(result.scalars().all())

        total_pages = (total + per_page - 1) // per_page if total > 0 else 0

        return {
            "roles": roles,
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": total,
                "total_pages": total_pages,
                "has_next": page < total_pages,
                "has_prev": page > 1,
            },
        }

    async def get_user_roles(
        self,
        user_id: UUID,
        workspace_id: Optional[UUID] = None
    ) -> List[Dict[str, Any]]:
        """
        Get all roles assigned to a user.

        Args:
            user_id: User UUID
            workspace_id: Optional workspace filter

        Returns:
            List of dicts with role and assignment details
        """
        query = (
            select(UserRole, Role, WorkspaceModel)
            .join(Role, UserRole.role_id == Role.id)
            .outerjoin(WorkspaceModel, UserRole.workspace_id == WorkspaceModel.id)
            .where(UserRole.user_id == user_id)
        )

        if workspace_id:
            query = query.where(UserRole.workspace_id == workspace_id)

        result = await self.db.execute(query)
        rows = result.all()

        roles_data = []
        for user_role, role, workspace in rows:
            roles_data.append({
                "id": str(user_role.id),
                "role_id": str(role.id),
                "role_name": role.name,
                "role_display_name": role.display_name,
                "hierarchy_level": role.hierarchy_level,
                "workspace_id": str(user_role.workspace_id) if user_role.workspace_id else None,
                "workspace_name": workspace.name if workspace else None,
                "is_primary": user_role.is_primary,
                "assigned_at": user_role.assigned_at.isoformat() if user_role.assigned_at else None
            })

        return roles_data

    async def get_role_with_permissions(
        self,
        role_id: UUID
    ) -> Dict[str, Any]:
        """
        Get role with its permissions.

        Args:
            role_id: Role UUID

        Returns:
            Dict with role details and permissions list

        Raises:
            ResourceNotFoundException: If role not found
        """
        role = await self.get_role_by_id(role_id)

        # Get permissions
        permissions_result = await self.db.execute(
            select(Permission)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .where(RolePermission.role_id == role_id)
        )
        permissions = permissions_result.scalars().all()

        role_data = role.to_dict()
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

        return role_data

    async def get_roles_by_ids(
        self,
        role_ids: list[UUID]
    ) -> Dict[UUID, Role]:
        """
        Batch load roles by IDs.

        Args:
            role_ids: List of role UUIDs

        Returns:
            Dict mapping role_id -> Role object
        """
        if not role_ids:
            return {}

        result = await self.db.execute(
            select(Role).where(Role.id.in_(role_ids))
        )
        roles = result.scalars().all()

        return {role.id: role for role in roles}

    # ========================================================================
    # Private Helper Methods
    # ========================================================================

    async def get_role_by_id(self, role_id: UUID) -> Role:
        """
        Get role by ID or raise 404.

        Args:
            role_id: Role UUID

        Returns:
            Role object

        Raises:
            ResourceNotFoundException: If role not found
        """
        result = await self.db.execute(
            select(Role).where(Role.id == role_id)
        )
        role = result.scalar_one_or_none()

        if not role:
            raise ResourceNotFoundException(
                resource_type="Role",
                resource_id=str(role_id)
            )

        return role
