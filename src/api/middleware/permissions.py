"""
Permission checking middleware for FastAPI.

This module provides dependency injection utilities for checking user permissions
before allowing access to protected endpoints.

Usage:
    from src.api.middleware.permissions import require_permissions, is_admin

    @router.get("/users")
    def get_users(
        _: None = Depends(require_permissions(["user.read"])),
        db: Session = Depends(get_db)
    ):
        return {"users": [...]}
"""

from typing import List, Optional
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.database.async_database import get_async_db as get_db
from src.api.security.dependencies import get_current_user
from src.utils.logger import logger


class PermissionChecker:
    """
    Dependency class for checking user permissions.

    This class is used as a FastAPI dependency to verify that the current user
    has the required permissions before allowing access to an endpoint.

    Usage in route:
        @router.get("/users")
        def get_users(
            current_user: dict = Depends(get_current_user),
            _: None = Depends(PermissionChecker(["user.read"]))
        ):
            ...
    """

    def __init__(
        self,
        required_permissions: List[str],
        require_all: bool = True,
        workspace_scoped: bool = False,
    ):
        """
        Initialize permission checker.

        Args:
            required_permissions: List of permission names required (e.g., ["user.read", "user.write"])
            require_all: If True, user must have ALL permissions. If False, ANY permission is sufficient.
            workspace_scoped: If True, check workspace-specific permissions from path/query params
        """
        self.required_permissions = required_permissions
        self.require_all = require_all
        self.workspace_scoped = workspace_scoped

    async def __call__(
        self,
        request: Request,
        current_user: dict = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ):
        """
        Check if current user has required permissions.

        This method is called by FastAPI's dependency injection system.

        Enhancements (Phase 1, Task 1.2):
        - Super admin bypass: super_admin role bypasses all permission checks
        - Enhanced workspace membership validation
        - Improved audit logging for permission denials

        Args:
            request: FastAPI request object
            current_user: Current authenticated user (from get_current_user dependency)
            db: Database session

        Raises:
            HTTPException: 401 if not authenticated, 403 if insufficient permissions

        Returns:
            True if permission check passes
        """
        user_id = current_user.get("identity")
        if not user_id:
            logger.warning(
                "Permission check failed: No user identity",
                extra={"required_permissions": self.required_permissions},
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required"
            )

        # Get workspace_id from request if workspace-scoped
        workspace_id = None
        if self.workspace_scoped:
            # Try path parameters first
            workspace_id = request.path_params.get("workspace_id")
            if not workspace_id:
                # Try query parameters
                workspace_id = request.query_params.get("workspace_id")

        # ENHANCEMENT 1: Check if user is super_admin (bypasses all permission checks)
        if await self._is_super_admin(db, user_id):
            logger.debug(
                f"Permission check passed for super_admin user {user_id}",
                extra={
                    "user_id": user_id,
                    "required_permissions": self.required_permissions,
                    "workspace_id": workspace_id,
                    "bypass_reason": "super_admin_role",
                },
            )
            return True

        # ENHANCEMENT 2: Enhanced workspace membership validation
        if self.workspace_scoped and workspace_id:
            is_member = await self._validate_workspace_membership(db, user_id, workspace_id)
            if not is_member:
                logger.warning(
                    f"Workspace access denied for user {user_id}: Not a workspace member",
                    extra={
                        "user_id": user_id,
                        "workspace_id": workspace_id,
                        "required_permissions": self.required_permissions,
                        "denial_reason": "not_workspace_member",
                    },
                )
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You are not a member of this workspace",
                )

        # Get user's permissions
        user_permissions = await self._get_user_permissions(db, user_id, workspace_id)

        # Check if user has required permissions
        has_permission = self._check_permissions(
            user_permissions, self.required_permissions, self.require_all
        )

        if not has_permission:
            # ENHANCEMENT 3: Improved audit logging for permission denials
            logger.warning(
                f"Permission denied for user {user_id}",
                extra={
                    "user_id": user_id,
                    "required_permissions": self.required_permissions,
                    "user_permissions": list(user_permissions),
                    "workspace_id": workspace_id,
                    "workspace_scoped": self.workspace_scoped,
                    "require_all": self.require_all,
                    "denial_reason": "insufficient_permissions",
                    "request_path": request.url.path,
                    "request_method": request.method,
                },
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. Required: {', '.join(self.required_permissions)}",
            )

        logger.debug(
            f"Permission check passed for user {user_id}",
            extra={
                "user_id": user_id,
                "required_permissions": self.required_permissions,
                "workspace_id": workspace_id,
            },
        )
        return True

    @staticmethod
    def _check_permissions(
        user_permissions: set, required_permissions: List[str], require_all: bool = True
    ) -> bool:
        """Check if user_permissions satisfies required_permissions."""
        if require_all:
            return all(p in user_permissions for p in required_permissions)
        return any(p in user_permissions for p in required_permissions)

    @staticmethod
    async def _get_user_permissions(
        db: AsyncSession, user_id: str, workspace_id: Optional[str] = None
    ) -> set:
        """
        Get all permissions for a user.

        Delegates to rbac_utils.get_user_permissions() which provides
        Redis caching with a 5-minute TTL for consistent performance.

        Args:
            db: Database session
            user_id: User ID (UUID as string)
            workspace_id: Optional workspace ID for workspace-scoped permissions

        Returns:
            Set of permission names (e.g., {"user.read", "user.write"})
        """
        from uuid import UUID as UUIDType

        from src.utils.rbac_utils import get_user_permissions

        # Convert string IDs to UUID objects as expected by rbac_utils
        user_uuid = UUIDType(user_id) if isinstance(user_id, str) else user_id
        workspace_uuid = (
            UUIDType(workspace_id)
            if workspace_id and isinstance(workspace_id, str)
            else workspace_id
        )

        permissions_list = await get_user_permissions(db, user_uuid, workspace_uuid)
        return set(permissions_list)

    @staticmethod
    async def _is_super_admin(db: AsyncSession, user_id: str) -> bool:
        """Check if user has super-admin level role (cached)."""
        from src.utils.rbac_utils import is_user_super_admin

        # Convert string ID to UUID object as expected by rbac_utils
        user_uuid = UUID(user_id) if isinstance(user_id, str) else user_id
        return await is_user_super_admin(db, user_uuid)

    @staticmethod
    async def _validate_workspace_membership(
        db: AsyncSession, user_id: str, workspace_id: str
    ) -> bool:
        """
        Validate that user is a member of the specified workspace.

        This provides enhanced security by ensuring users can only access
        workspaces they are actually members of, even if they somehow have
        workspace-scoped permissions.

        Args:
            db: Database session
            user_id: User ID (UUID as string)
            workspace_id: Workspace ID (UUID as string)

        Returns:
            True if user is a workspace member, False otherwise
        """
        from sqlalchemy import select

        from src.api.models.workspace_models.workspace_member import WorkspaceMembers

        # Check if user is a workspace member
        query = select(WorkspaceMembers).where(
            WorkspaceMembers.user_id == user_id, WorkspaceMembers.workspace_id == workspace_id
        )
        result = await db.execute(query)
        member = result.scalars().first()

        # Also check if user has super_admin role (can access any workspace)
        if not member:
            return False

        return True


def require_permissions(
    permissions: List[str], require_all: bool = True, workspace_scoped: bool = False
):
    """
    Decorator factory for permission checking.

    This is a convenience function that creates a PermissionChecker instance
    for use as a FastAPI dependency.

    Args:
        permissions: List of required permissions (e.g., ["user.read", "user.write"])
        require_all: If True, require ALL permissions. If False, require ANY permission.
        workspace_scoped: If True, check workspace-specific permissions.

    Returns:
        PermissionChecker instance (FastAPI dependency)

    Example:
        @router.get("/users")
        def get_users(
            _: None = Depends(require_permissions(["user.read"])),
            db: Session = Depends(get_db)
        ):
            return {"users": [...]}

        @router.post("/content")
        def create_content(
            _: None = Depends(require_permissions(["content.create", "content.write"], require_all=False)),
            db: Session = Depends(get_db)
        ):
            return {"content": "created"}

        @router.get("/workspaces/{workspace_id}/members")
        def get_workspace_members(
            workspace_id: str,
            _: None = Depends(require_permissions(["workspace.manage_members"], workspace_scoped=True)),
            db: Session = Depends(get_db)
        ):
            return {"members": [...]}
    """
    return PermissionChecker(permissions, require_all, workspace_scoped)


async def is_admin(
    current_user: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> bool:
    """
    Check if current user is an admin.

    This is a convenience dependency that checks if the user has
    hierarchy_level >= 90 (cached via rbac_utils).
    """
    from src.utils.rbac_utils import is_user_admin

    user_id = current_user.get("identity")

    if not user_id:
        logger.warning("Admin check failed: No user identity", extra={"check_type": "is_admin"})
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required"
        )

    # Convert string ID to UUID object as expected by rbac_utils
    user_uuid = UUID(user_id) if isinstance(user_id, str) else user_id

    # Check if user has admin-level role (cached)
    is_authorized = await is_user_admin(db, user_uuid)

    if not is_authorized:
        logger.warning(
            f"Admin access denied for user {user_id}",
            extra={
                "user_id": user_id,
                "check_type": "is_admin",
                "denial_reason": "not_admin_or_super_admin",
            },
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")

    logger.debug(
        f"Admin check passed for user {user_id}",
        extra={"user_id": user_id, "check_type": "is_admin"},
    )
    return True
