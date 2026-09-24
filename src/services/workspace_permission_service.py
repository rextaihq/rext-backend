"""Service for managing workspace-specific permissions."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.middleware.exceptions import (
    ResourceNotFoundException,
    RextAuthorizationException,
)
from src.api.models.user_models.permissions import Permission
from src.api.models.user_models.roles import Role
from src.api.models.user_models.user_roles import UserRole
from src.api.models.workspace_models.workspace_member import WorkspaceMembers
from src.api.models.workspace_models.workspace_model import WorkspaceModel
from src.utils.logger import logger


class WorkspacePermissionService:
    """Service for workspace permission operations."""

    @staticmethod
    async def get_user_workspace_permissions(
        db: AsyncSession, user_id: UUID, workspace_id: UUID
    ) -> dict:
        """
        Get user's role and permissions for a specific workspace.

        Raises:
            ResourceNotFoundException: Workspace does not exist
            RextAuthorizationException: User has no access
        """
        from src.utils.rbac_utils import get_user_permissions, is_user_admin

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
        is_workspace_owner = workspace.user_id == user_id

        # Membership is the gate here, not roles. Accounts may carry no global
        # role at all (the former 'user' floor role is gone), so a role-name
        # check could never be the authority. This endpoint is also how the
        # client discovers its own permissions, so it must not require a
        # permission of its own - gating it on member.read deadlocked any role
        # that lacks member.read.
        if not is_platform_admin and not is_workspace_owner:
            member_result = await db.execute(
                select(WorkspaceMembers).where(
                    WorkspaceMembers.workspace_id == workspace_id,
                    WorkspaceMembers.user_id == user_id,
                    WorkspaceMembers.status == "active",
                )
            )
            if member_result.scalar_one_or_none() is None:
                raise RextAuthorizationException(
                    message="User does not have access to workspace",
                    resource=f"workspace:{workspace_id}",
                )

        # Highest workspace-scoped role, for display. Taking all_role_names[0]
        # could report "user" as the member's role, since that list mixes in
        # the global role and has no defined ordering.
        scoped_role_result = await db.execute(
            select(Role.name)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(
                UserRole.user_id == user_id,
                UserRole.workspace_id == workspace_id,
            )
            .order_by(Role.hierarchy_level.desc())
            .limit(1)
        )
        scoped_role = scoped_role_result.scalar_one_or_none()

        if is_platform_admin:
            highest_role = "admin"
        elif is_workspace_owner or scoped_role == "workspace_owner":
            highest_role = "workspace_owner"
        else:
            # Display label for a member holding no workspace-scoped role
            # (the former global 'user' floor role no longer exists).
            highest_role = scoped_role or "member"

        # 2. Get the actual UNION of permissions from rbac_utils
        # This is the single source of truth used by decorators
        permissions = await get_user_permissions(db, user_id, workspace_id)

        # 3. If they are the workspace owner record, ensure they have ALL relevant permissions
        # even if the role mapping in DB is broken/incomplete.
        if is_workspace_owner:
            owner_permissions_result = await db.execute(
                select(Permission.name).where(
                    Permission.resource.in_(
                        [
                            "workspace",
                            "content",
                            "topic",
                            "knowledge",
                            "member",
                            "subscription",
                            "billing",
                            "usage",
                            "media",
                            "license",
                        ]
                    )
                )
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
                "permission_count": len(permissions),
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
        db: AsyncSession, user_id: UUID, workspace_id: UUID, permission: str
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
