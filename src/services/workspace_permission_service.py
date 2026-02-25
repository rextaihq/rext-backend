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

        from src.utils.rbac_utils import get_user_roles, get_user_permissions, ADMIN_HIERARCHY_THRESHOLD

        # Get all roles the user has that apply to this workspace (global or scoped)
        roles_with_context = await get_user_roles(db, user_id, workspace_id)
        
        if not roles_with_context:
            raise RextAuthorizationException(
                message="User does not have access to workspace",
                resource=f"workspace:{workspace_id}",
            )

        # Sort by hierarchy level to find the highest role
        roles_with_context.sort(key=lambda x: x[0].hierarchy_level, reverse=True)
        highest_role = roles_with_context[0][0]

        # If highest role is admin level (>=80), return all system permissions
        # This covers super_admin (100), support_admin (90), and platform_admin (80)
        if highest_role.hierarchy_level >= ADMIN_HIERARCHY_THRESHOLD:
            # Admin bypass - return all permissions in the system
            all_permissions_result = await db.execute(select(Permission.name))
            raw_perms = [row[0] for row in all_permissions_result.all()]
            
            # Global Permission Bridge: Ensure both dot and colon notation are supported.
            permissions_list = list(raw_perms)
            colon_perms = [p.replace('.', ':') for p in permissions_list if '.' in p]
            if colon_perms:
                permissions_list.extend(colon_perms)
            permissions = sorted(list(set(permissions_list)))
        else:
            # Return union of permissions from all applicable roles
            # (get_user_permissions already aggregates global + workspace-scoped and handles the bridge)
            permissions = await get_user_permissions(db, user_id, workspace_id)

        logger.info(
            "Loaded workspace permissions",
            extra={
                "user_id": str(user_id),
                "workspace_id": str(workspace_id),
                "highest_role": highest_role.name,
                "permission_count": len(permissions),
            },
        )

        return {
            "workspace_id": str(workspace_id),
            "workspace_slug": workspace.slug,
            "user_role": highest_role.name,
            "permissions": list(permissions),
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
