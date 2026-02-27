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
        from src.utils.rbac_utils import get_user_permissions, get_user_role_names, is_user_admin

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

        # 1. Determine the user's highest role name for the response
        # Check if user is the platform admin first
        is_platform_admin = await is_user_admin(db, user_id)
        
        # Check if user is the workspace owner (the user who created it)
        is_workspace_owner = (workspace.user_id == user_id)

        # Fetch all role names for accurate status reporting
        all_role_names = await get_user_role_names(db, user_id, workspace_id)
        
        if is_workspace_owner and "workspace_owner" not in all_role_names:
            # Add it to the list for display if they are the owner record but role mapping is missing
            all_role_names.append("workspace_owner")

        # Determine highest role for display
        if is_platform_admin:
            highest_role = "admin"
        elif is_workspace_owner or "workspace_owner" in all_role_names:
            highest_role = "workspace_owner"
        elif all_role_names:
            highest_role = all_role_names[0] # Simplification, could use hierarchy
        else:
            # If they have no roles in the workspace AND aren't the owner record, 
            # they shouldn't even reach here if they aren't global admins.
            if not is_platform_admin:
                 raise RextAuthorizationException(
                    message="User does not have access to workspace",
                    resource=f"workspace:{workspace_id}",
                )
            highest_role = "admin"

        # 2. Get the actual UNION of permissions from rbac_utils
        # This is the single source of truth used by decorators
        permissions = await get_user_permissions(db, user_id, workspace_id)

        # 3. If they are the workspace owner record, ensure they have ALL relevant permissions
        # even if the role mapping in DB is broken/incomplete.
        if is_workspace_owner:
            owner_permissions_result = await db.execute(
                select(Permission.name)
                .where(Permission.resource.in_([
                    'workspace', 'content', 'topic', 'knowledge', 'member', 'subscription', 'billing', 'usage', 'media', 'license'
                ]))
            )
            owner_perms = [row[0] for row in owner_permissions_result.all()]
            # Merge with existing permissions
            permissions = list(set(permissions) | set(owner_perms))

        logger.info(
            "Loaded workspace permissions",
            extra={
                "user_id": str(user_id),
                "workspace_id": str(workspace_id),
                "highest_role": highest_role,
                "permission_count": len(permissions)
            },
        )

        return {
            "workspace_id": str(workspace_id),
            "workspace_slug": workspace.slug,
            "user_role": highest_role,
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
