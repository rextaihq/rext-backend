"""Business logic for permission management."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.middleware.exceptions import (
    DuplicateResourceException,
    ResourceNotFoundException,
    RextAuthorizationException,
    RextValidationException,
)
from src.api.models.user_models.permissions import Permission
from src.api.models.user_models.role_permissions import RolePermission
from src.api.models.user_models.roles import Role
from src.api.models.user_models.user_roles import UserRole
from src.api.schema.permission_schema import PermissionCreate, PermissionUpdate
from sqlalchemy.exc import IntegrityError
from src.utils.logger import logger


class PermissionService:
    """Encapsulate business logic for permission CRUD operations."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_permissions(
        self,
        user_id: UUID,
        resource: Optional[str] = None,
        include_roles: bool = False,
        page: int = 1,
        per_page: int = 50,
    ) -> Dict[str, Any]:
        await self._ensure_user_can(user_id, "permission.read")

        base_query = select(Permission)
        if resource:
            base_query = base_query.where(Permission.resource == resource)

        # Get total count
        count_query = select(func.count()).select_from(base_query.subquery())
        count_result = await self.db.execute(count_query)
        total = count_result.scalar() or 0

        # Apply pagination
        offset = (page - 1) * per_page
        result = await self.db.execute(
            base_query.order_by(Permission.resource, Permission.action)
            .offset(offset)
            .limit(per_page)
        )
        permissions = result.scalars().all()

        if include_roles:
            permissions_data = await self._serialize_permissions_with_roles_batch(permissions)
        else:
            permissions_data = [permission.to_dict() for permission in permissions]

        total_pages = (total + per_page - 1) // per_page if total > 0 else 0

        return {
            "data": {
                "permissions": permissions_data,
                "count": len(permissions_data),
                "pagination": {
                    "page": page,
                    "per_page": per_page,
                    "total": total,
                    "total_pages": total_pages,
                    "has_next": page < total_pages,
                    "has_prev": page > 1,
                },
            },
            "message": f"Retrieved {len(permissions_data)} permissions",
        }

    async def get_permission(
        self,
        user_id: UUID,
        permission_id: UUID,
        include_roles: bool = False,
    ) -> Dict[str, Any]:
        await self._ensure_user_can(user_id, "permission.read")
        permission = await self._get_permission_or_404(permission_id)

        if include_roles:
            permission_data = await self._serialize_permission_with_roles(permission)
        else:
            permission_data = permission.to_dict()

        return {
            "data": {"permission": permission_data},
            "message": "Permission retrieved successfully",
        }

    async def create_permission(
        self,
        user_id: UUID,
        payload: PermissionCreate,
    ) -> Dict[str, Any]:
        await self._ensure_user_can(user_id, "permission.create")

        expected_name = f"{payload.resource.lower()}.{payload.action.lower()}"
        if payload.name.lower() != expected_name:
            raise RextValidationException(
                message=f"Permission name must match format: {expected_name}",
                context={"provided": payload.name, "expected": expected_name},
            )

        await self._ensure_unique_name(payload.name)

        permission = Permission(
            name=payload.name.lower(),
            display_name=payload.display_name,
            description=payload.description,
            resource=payload.resource.lower(),
            action=payload.action.lower(),
        )

        self.db.add(permission)
        try:
            await self.db.flush()
        except IntegrityError as e:
            await self.db.rollback()
            if "uq_permissions_name" in str(e.orig):
                raise DuplicateResourceException(
                    message="Permission with this name already exists",
                    resource_type="permission",
                    conflicting_field="name",
                    conflicting_value=payload.name,
                )
            raise
        await self.db.refresh(permission)

        logger.info(
            "Permission created",
            extra={"permission": permission.name, "user_id": str(user_id)},
        )

        return {
            "data": {"permission": permission.to_dict()},
            "message": f"Permission '{permission.name}' created successfully",
        }

    async def update_permission(
        self,
        user_id: UUID,
        permission_id: UUID,
        payload: PermissionUpdate,
    ) -> Dict[str, Any]:
        await self._ensure_user_can(user_id, "permission.update")
        permission = await self._get_permission_or_404(permission_id)

        if payload.display_name is not None:
            permission.display_name = payload.display_name

        if payload.description is not None:
            permission.description = payload.description

        await self.db.flush()
        await self.db.refresh(permission)

        logger.info(
            "Permission updated",
            extra={"permission": permission.name, "user_id": str(user_id)},
        )

        return {
            "data": {"permission": permission.to_dict()},
            "message": f"Permission '{permission.name}' updated successfully",
        }

    async def delete_permission(
        self,
        user_id: UUID,
        permission_id: UUID,
    ) -> Dict[str, Any]:
        await self._ensure_user_can(user_id, "permission.delete")
        permission = await self._get_permission_or_404(permission_id)

        if permission.is_system:
            raise RextValidationException(
                message=f"Cannot delete system permission '{permission.name}'",
                field_errors={"permission_id": ["System permissions cannot be deleted"]},
            )

        result = await self.db.execute(
            select(func.count(RolePermission.role_id)).where(RolePermission.permission_id == permission_id)
        )
        assignment_count = result.scalar() or 0
        if assignment_count > 0:
            raise RextValidationException(
                message=f"Cannot delete permission assigned to {assignment_count} role(s)",
                context={"permission_id": str(permission_id), "role_count": assignment_count},
            )

        permission_name = permission.name
        await self.db.delete(permission)
        await self.db.flush()

        logger.info(
            "Permission deleted",
            extra={"permission": permission_name, "user_id": str(user_id)},
        )

        return {
            "data": {"permission_id": str(permission_id)},
            "message": f"Permission '{permission_name}' deleted successfully",
        }
    async def assign_permissions_to_role(
        self,
        *,
        role_id: UUID,
        permission_ids: list[UUID],
    ) -> Dict[str, Any]:
        role = await self._get_role_or_404(role_id)

        result = await self.db.execute(
            select(RolePermission.permission_id).where(RolePermission.role_id == role_id)
        )
        existing_ids = {row[0] for row in result.all()}

        added = 0
        skipped = 0
        invalid = 0

        for permission_id in permission_ids:
            if permission_id in existing_ids:
                skipped += 1
                continue

            permission = await self._get_permission_or_none(permission_id)
            if not permission:
                invalid += 1
                continue

            self.db.add(RolePermission(role_id=role_id, permission_id=permission_id))
            added += 1

        if added:
            await self.db.flush()
            # Invalidate permission cache for all users with this role
            await self._invalidate_role_users_cache(role_id)

        logger.info(
            "Assigned permissions to role",
            extra={
                "role_id": str(role_id),
                "added": added,
                "skipped": skipped,
                "invalid": invalid,
            },
        )

        return {
            "role_id": str(role_id),
            "role_name": role.name,
            "added_count": added,
            "skipped_count": skipped,
            "invalid_count": invalid,
        }
    async def revoke_permission_from_role(
        self,
        *,
        role_id: UUID,
        permission_id: UUID,
    ) -> Dict[str, Any]:
        result = await self.db.execute(
            select(RolePermission).where(
                RolePermission.role_id == role_id,
                RolePermission.permission_id == permission_id,
            )
        )
        assignment = result.scalar_one_or_none()
        if not assignment:
            raise ResourceNotFoundException(
                message="Permission assignment not found",
                context={"role_id": str(role_id), "permission_id": str(permission_id)},
            )

        role = await self._get_role_or_404(role_id)
        permission = await self._get_permission_or_404(permission_id)

        await self.db.delete(assignment)

        # Invalidate permission cache for all users with this role
        await self._invalidate_role_users_cache(role_id)

        logger.info(
            "Revoked permission from role",
            extra={"role_id": str(role_id), "permission_id": str(permission_id)},
        )

        return {
            "role_id": str(role_id),
            "role_name": role.name,
            "permission_id": str(permission_id),
            "permission_name": permission.name,
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _ensure_user_can(self, user_id: UUID, permission_name: str) -> None:
        """Check if user has permission or is admin. Raises RextAuthorizationException on denial."""
        from src.utils.rbac_utils import check_permission_or_admin
        await check_permission_or_admin(
            self.db, user_id, permission_name,
            raise_on_deny=True, use_http_exception=False
        )


    async def _get_permission_or_404(self, permission_id: UUID) -> Permission:
        result = await self.db.execute(
            select(Permission).where(Permission.id == permission_id)
        )
        permission = result.scalar_one_or_none()
        if not permission:
            raise ResourceNotFoundException(
                resource_type="permission",
                resource_id=str(permission_id),
            )
        return permission

    async def _get_permission_or_none(self, permission_id: UUID) -> Optional[Permission]:
        result = await self.db.execute(select(Permission).where(Permission.id == permission_id))
        return result.scalar_one_or_none()

    async def _get_role_or_404(self, role_id: UUID) -> Role:
        result = await self.db.execute(select(Role).where(Role.id == role_id))
        role = result.scalar_one_or_none()
        if not role:
            raise ResourceNotFoundException(resource_type="role", resource_id=str(role_id))
        return role

    async def _serialize_permissions_with_roles_batch(
        self, permissions: list[Permission]
    ) -> list[Dict[str, Any]]:
        """Batch-load roles for all permissions in a single query to avoid N+1."""
        if not permissions:
            return []

        permission_ids = [p.id for p in permissions]

        # Single query to fetch all role-permission mappings
        result = await self.db.execute(
            select(RolePermission.permission_id, Role)
            .join(Role, RolePermission.role_id == Role.id)
            .where(RolePermission.permission_id.in_(permission_ids))
        )
        rows = result.all()

        # Group roles by permission_id
        roles_by_permission: Dict[Any, list] = {}
        for perm_id, role in rows:
            roles_by_permission.setdefault(perm_id, []).append(role)

        # Build serialized list
        permissions_data = []
        for permission in permissions:
            permission_dict = permission.to_dict()
            permission_dict["roles"] = [
                {
                    "id": str(role.id),
                    "name": role.name,
                    "display_name": role.display_name,
                    "hierarchy_level": role.hierarchy_level,
                }
                for role in roles_by_permission.get(permission.id, [])
            ]
            permissions_data.append(permission_dict)

        return permissions_data

    async def _serialize_permission_with_roles(self, permission: Permission) -> Dict[str, Any]:
        """Serialize a single permission with its roles. Uses batch method internally."""
        results = await self._serialize_permissions_with_roles_batch([permission])
        return results[0] if results else permission.to_dict()

    async def _ensure_unique_name(self, name: str, exclude_id: Optional[UUID] = None) -> None:
        query = select(Permission).where(func.lower(Permission.name) == name.lower())
        if exclude_id:
            query = query.where(Permission.id != exclude_id)

        result = await self.db.execute(query)
        if result.scalar_one_or_none():
            raise DuplicateResourceException(
                message="Permission with this name already exists",
                context={"name": name},
            )
    async def _invalidate_role_users_cache(self, role_id: UUID) -> None:
        """
        Invalidate permission cache for all users assigned to a specific role.

        When permissions on a role change (added or revoked), all users holding
        that role may have stale cached permissions. This method queries all
        user_role assignments for the given role and invalidates each user's
        permission cache in Redis.

        Args:
            role_id: UUID of the role whose users' caches should be invalidated
        """
        from src.api.cache.decorators import invalidate_cache

        # Find all users assigned to this role
        result = await self.db.execute(
            select(UserRole.user_id).where(UserRole.role_id == role_id)
        )
        user_ids = [row[0] for row in result.all()]

        if not user_ids:
            logger.debug(
                "No users assigned to role, skipping cache invalidation",
                extra={"role_id": str(role_id)}
            )
            return

        # Invalidate cache for each affected user
        invalidated_count = 0
        for user_id in user_ids:
            deleted = await invalidate_cache(f"user:permissions:{user_id}:*")
            invalidated_count += deleted

        logger.info(
            "Invalidated permission cache for role users",
            extra={
                "role_id": str(role_id),
                "affected_users": len(user_ids),
                "cache_keys_deleted": invalidated_count
            }
        )