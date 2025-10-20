"""Service for managing workspace-specific permissions."""

from typing import List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.models.user_models.permissions import Permission
from src.api.models.user_models.role_permissions import RolePermission
from src.api.models.user_models.roles import Role
from src.api.models.user_models.user_roles import UserRole
from src.api.models.workspace_models.workspace_model import WorkspaceModel
from src.utils.logger import logger


class WorkspacePermissionService:
    """Service for workspace permission operations."""

    @staticmethod
    async def get_user_workspace_permissions(
        db: AsyncSession,
        user_id: UUID,
        workspace_id: UUID
    ) -> dict:
        """
        Get user's role and permissions for a specific workspace.

        Args:
            db: Database session
            user_id: User ID
            workspace_id: Workspace ID

        Returns:
            Dict with workspace_id, workspace_slug, user_role, and permissions list

        Raises:
            ValueError: If workspace not found or user doesn't have access
        """
        # Check if workspace exists
        workspace_result = await db.execute(
            select(WorkspaceModel).where(WorkspaceModel.id == workspace_id)
        )
        workspace = workspace_result.scalar_one_or_none()

        if not workspace:
            raise ValueError(f"Workspace {workspace_id} not found")

        # Get user's workspace role
        user_role_result = await db.execute(
            select(UserRole, Role)
            .join(Role, Role.id == UserRole.role_id)
            .where(UserRole.user_id == user_id)
            .where(UserRole.workspace_id == workspace_id)
        )
        user_role_data = user_role_result.first()

        if not user_role_data:
            # Check if user is super_admin (has access to all workspaces)
            super_admin_check = await db.execute(
                select(UserRole, Role)
                .join(Role, Role.id == UserRole.role_id)
                .where(UserRole.user_id == user_id)
                .where(UserRole.workspace_id == None)
                .where(Role.name == 'super_admin')
            )
            is_super_admin = super_admin_check.first() is not None

            if is_super_admin:
                # Super admin gets all permissions
                all_permissions_result = await db.execute(
                    select(Permission.name)
                    .where(Permission.resource.in_([
                        'workspace', 'content', 'topic', 'knowledge', 'member'
                    ]))
                )
                all_permissions = [row[0] for row in all_permissions_result.all()]

                return {
                    "workspace_id": str(workspace_id),
                    "workspace_slug": workspace.slug,
                    "user_role": "super_admin",
                    "permissions": all_permissions
                }

            raise ValueError(f"User {user_id} does not have access to workspace {workspace_id}")

        user_role, role = user_role_data

        # Get permissions for the user's workspace role
        permissions_result = await db.execute(
            select(Permission.name)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .where(RolePermission.role_id == role.id)
            .distinct()
        )
        permissions = [row[0] for row in permissions_result.all()]

        logger.info(
            f"Loaded workspace permissions for user {user_id} in workspace {workspace_id}",
            extra={
                "user_id": str(user_id),
                "workspace_id": str(workspace_id),
                "role": role.name,
                "permission_count": len(permissions)
            }
        )

        return {
            "workspace_id": str(workspace_id),
            "workspace_slug": workspace.slug,
            "user_role": role.name,
            "permissions": permissions
        }

    @staticmethod
    async def get_user_workspace_permissions_by_slug(
        db: AsyncSession,
        user_id: UUID,
        workspace_slug: str
    ) -> dict:
        """
        Get user's permissions for workspace by slug.

        Args:
            db: Database session
            user_id: User ID
            workspace_slug: Workspace slug

        Returns:
            Dict with workspace permissions

        Raises:
            ValueError: If workspace not found or user doesn't have access
        """
        # Get workspace by slug
        workspace_result = await db.execute(
            select(WorkspaceModel).where(WorkspaceModel.slug == workspace_slug)
        )
        workspace = workspace_result.scalar_one_or_none()

        if not workspace:
            raise ValueError(f"Workspace with slug '{workspace_slug}' not found")

        return await WorkspacePermissionService.get_user_workspace_permissions(
            db, user_id, workspace.id
        )

    @staticmethod
    async def check_user_permission(
        db: AsyncSession,
        user_id: UUID,
        workspace_id: UUID,
        permission: str
    ) -> bool:
        """
        Check if user has specific permission in workspace.

        Args:
            db: Database session
            user_id: User ID
            workspace_id: Workspace ID
            permission: Permission name (e.g., "topic.create")

        Returns:
            True if user has permission, False otherwise
        """
        try:
            perms = await WorkspacePermissionService.get_user_workspace_permissions(
                db, user_id, workspace_id
            )
            return permission in perms["permissions"]
        except ValueError:
            return False
