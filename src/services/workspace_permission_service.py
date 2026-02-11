"""Service for managing workspace-specific permissions."""

from uuid import UUID
from sqlalchemy import select, distinct
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.models.user_models.permissions import Permission
from src.api.models.user_models.role_permissions import RolePermission
from src.api.models.user_models.roles import Role
from src.api.models.user_models.user_roles import UserRole
from src.api.models.workspace_models.workspace_model import WorkspaceModel
from src.api.middleware.exceptions import (
    ResourceNotFoundException,
    RextAuthorizationException,
)
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

        Raises:
            ResourceNotFoundException: Workspace does not exist
            RextAuthorizationException: User has no access
        """

        # Check workspace exists
        result = await db.execute(
            select(WorkspaceModel).where(
                WorkspaceModel.id == workspace_id,
                WorkspaceModel.deleted_at.is_(None),
            )
        )
        workspace = result.scalar_one_or_none()

        if not workspace:
            raise ResourceNotFoundException(
                resource_type="workspace",
                resource_id=str(workspace_id),
            )

        # Check super admin
        super_admin_result = await db.execute(
            select(UserRole)
            .join(Role, Role.id == UserRole.role_id)
            .where(
                UserRole.user_id == user_id,
                UserRole.workspace_id.is_(None),
                Role.name == "super_admin",
            )
        )

        if super_admin_result.first():
            perms_result = await db.execute(
                select(distinct(Permission.name))
            )
            permissions = [row[0] for row in perms_result.all()]

            return {
                "workspace_id": str(workspace_id),
                "workspace_slug": workspace.slug,
                "user_role": "super_admin",
                "permissions": permissions,
            }

        # Workspace role
        role_result = await db.execute(
            select(UserRole, Role)
            .join(Role, Role.id == UserRole.role_id)
            .where(
                UserRole.user_id == user_id,
                UserRole.workspace_id == workspace_id,
            )
        )
        role_data = role_result.first()

        if not role_data:
            raise RextAuthorizationException(
                message="User does not have access to workspace",
                resource=f"workspace:{workspace_id}",
            )

        user_role, role = role_data

        perms_result = await db.execute(
            select(Permission.name)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .where(RolePermission.role_id == role.id)
            .distinct()
        )
        permissions = [row[0] for row in perms_result.all()]

        logger.info(
            "Loaded workspace permissions",
            extra={
                "user_id": str(user_id),
                "workspace_id": str(workspace_id),
                "role": role.name,
            },
        )

        return {
            "workspace_id": str(workspace_id),
            "workspace_slug": workspace.slug,
            "user_role": role.name,
            "permissions": permissions,
        }

    @staticmethod
    async def check_user_permission(
        db: AsyncSession,
        user_id: UUID,
        workspace_id: UUID,
        permission: str
    ) -> bool:
        """
        Check if user has a specific permission.

        Raises:
            ResourceNotFoundException
            RextAuthorizationException
        """
        perms = await WorkspacePermissionService.get_user_workspace_permissions(
            db, user_id, workspace_id
        )
        return permission in perms["permissions"]
