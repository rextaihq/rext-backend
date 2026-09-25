"""
Impersonation Service - Business Logic for User Impersonation

This service encapsulates all business logic related to admin user
impersonation, including permission validation and token generation.

Responsibilities:
- Start impersonation (with permission checks)
- Stop impersonation
- Track impersonation status
- Generate impersonation tokens

Does NOT:
- Handle HTTP requests/responses (that's routes)
- Commit transactions (that's decorators/routes)
- Create actual JWT tokens (that's token utils)
"""

from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.middleware.exceptions import (
    ResourceNotFoundException,
    RextAuthenticationException,
    RextValidationException,
)
from src.api.models.user_models.impersonation_session import ImpersonationSession
from src.api.models.user_models.permissions import Permission
from src.api.models.user_models.role_permissions import RolePermission
from src.api.models.user_models.roles import Role
from src.api.models.user_models.user_roles import UserRole
from src.api.models.user_models.users import Users
from src.utils.logger import logger


class ImpersonationService:
    """Service for user impersonation management"""

    def __init__(self, db: AsyncSession):
        """
        Initialize ImpersonationService.

        Args:
            db: Async database session
        """
        self.db = db

    async def start_impersonation(
        self, admin_user_id: UUID, target_user_id: UUID
    ) -> Dict[str, Any]:
        """
        Start impersonating a user.

        Business Rules:
        - Admin must have user.impersonate permission
        - Cannot impersonate yourself
        - Cannot impersonate another admin with higher/equal permissions
        - Target user must exist and be active

        Args:
            admin_user_id: Admin user UUID
            target_user_id: Target user UUID to impersonate

        Returns:
            Dict with target user info and impersonation metadata

        Raises:
            ResourceNotFoundException: If users not found
            RextValidationException: If validation fails
            RextAuthenticationException: If permission denied
        """
        # Get admin user
        admin_user = await self._get_user_or_404(admin_user_id)

        # Get target user
        target_user = await self._get_user_or_404(target_user_id)

        # Cannot impersonate yourself
        if admin_user_id == target_user_id:
            raise RextValidationException(
                message="Cannot impersonate yourself",
                field_errors={"target_user_id": ["Self-impersonation not allowed"]},
            )

        # Check if admin has impersonation permission
        has_permission = await self._has_impersonation_permission(admin_user_id)

        if not has_permission:
            raise RextAuthenticationException(
                message="You do not have permission to impersonate users",
                context={"admin_user_id": str(admin_user_id)},
            )

        # Check target user status
        if target_user.status != "active":
            raise RextValidationException(
                message="Cannot impersonate inactive user",
                field_errors={"target_user_id": ["User is not active"]},
            )

        # Only verified users can be impersonated: an unverified account is
        # still mid-signup (no confirmed mailbox) and cannot log in itself,
        # so acting as it via impersonation would bypass that gate.
        if not target_user.email_verified:
            raise RextValidationException(
                message="Cannot impersonate a user who hasn't verified their email address",
                field_errors={
                    "target_user_id": ["User email is not verified"]
                },
            )

        # Prevent impersonating higher privilege users
        admin_max_hierarchy = await self._get_max_hierarchy_level(admin_user_id)
        target_max_hierarchy = await self._get_max_hierarchy_level(target_user_id)

        if target_max_hierarchy >= admin_max_hierarchy:
            raise RextAuthenticationException(
                message="Cannot impersonate user with equal or higher privilege level",
                context={
                    "admin_hierarchy": admin_max_hierarchy,
                    "target_hierarchy": target_max_hierarchy,
                },
            )

        logger.info(
            f"Admin {admin_user_id} started impersonating {target_user_id}",
            extra={
                "admin_user_id": str(admin_user_id),
                "target_user_id": str(target_user_id),
                "admin_email": admin_user.email,
                "target_email": target_user.email,
            },
        )

        target_context = await self._build_context_from_user(target_user)

        return {
            "target_user_id": target_context["user_id"],
            "target_email": target_context["email"],
            "target_full_name": target_context["full_name"],
            "target_display_name": target_context["display_name"],
            "impersonated_by": str(admin_user_id),
            "impersonated_by_email": admin_user.email,
            "impersonation_started_at": datetime.now(timezone.utc).isoformat(),
            "roles": target_context["roles"],
            "permissions": target_context["permissions"],
        }

    async def stop_impersonation(self, admin_user_id: UUID, target_user_id: UUID) -> Dict[str, str]:
        """
        Stop impersonating a user.

        Args:
            admin_user_id: Admin user UUID
            target_user_id: Target user UUID being impersonated

        Returns:
            Dict with impersonation stop info
        """
        logger.info(
            f"Admin {admin_user_id} stopped impersonating {target_user_id}",
            extra={"admin_user_id": str(admin_user_id), "target_user_id": str(target_user_id)},
        )

        return {
            "message": "Impersonation stopped",
            "admin_user_id": str(admin_user_id),
            "impersonation_stopped_at": datetime.now(timezone.utc).isoformat(),
        }

    async def get_impersonation_status(
        self, user_id: UUID, impersonating_user_id: Optional[UUID] = None
    ) -> Dict[str, Any]:
        """
        Get current impersonation status.

        Args:
            user_id: Current user UUID
            impersonating_user_id: Optional impersonating user UUID (from token)

        Returns:
            Dict with is_impersonating flag and details
        """
        if not impersonating_user_id:
            return {"is_impersonating": False, "user_id": str(user_id)}

        # Get both users
        user = await self._get_user_or_404(user_id)
        impersonating_user = await self._get_user_or_404(impersonating_user_id)

        return {
            "is_impersonating": True,
            "user_id": str(user_id),
            "user_email": user.email,
            "impersonated_by_user_id": str(impersonating_user_id),
            "impersonated_by_email": impersonating_user.email,
        }

    # ========================================================================
    # Private Helper Methods
    # ========================================================================

    async def _get_user_or_404(self, user_id: UUID) -> Users:
        """
        Get user or raise 404.

        Args:
            user_id: User UUID

        Returns:
            Users object

        Raises:
            ResourceNotFoundException: If user not found
        """
        result = await self.db.execute(select(Users).where(Users.id == user_id))
        user = result.scalar_one_or_none()

        if not user:
            raise ResourceNotFoundException(resource_type="User", resource_id=str(user_id))

        return user

    async def _has_impersonation_permission(self, user_id: UUID) -> bool:
        """
        Check if user has user.impersonate permission.

        Args:
            user_id: User UUID

        Returns:
            True if has permission, False otherwise
        """
        result = await self.db.execute(
            select(Permission)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .join(Role, Role.id == RolePermission.role_id)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(UserRole.user_id == user_id, Permission.name == "user.impersonate")
        )
        permission = result.scalar_one_or_none()

        return permission is not None

    async def _get_max_hierarchy_level(self, user_id: UUID) -> int:
        """
        Get maximum hierarchy level from user's roles.

        Args:
            user_id: User UUID

        Returns:
            Maximum hierarchy level (0 if no roles)
        """
        result = await self.db.execute(
            select(Role.hierarchy_level)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(UserRole.user_id == user_id)
            .order_by(Role.hierarchy_level.desc())
            .limit(1)
        )
        max_level = result.scalar_one_or_none()

        return max_level or 0

    async def _get_auth_context(self, user_id: UUID) -> Dict[str, Any]:
        """Fetch global roles and permissions for target user."""
        roles_result = await self.db.execute(
            select(Role.name)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(UserRole.user_id == user_id, UserRole.workspace_id.is_(None))
        )
        roles = [row[0] for row in roles_result.all()]

        permissions_result = await self.db.execute(
            select(Permission.name)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .join(UserRole, UserRole.role_id == RolePermission.role_id)
            .where(UserRole.user_id == user_id, UserRole.workspace_id.is_(None))
            .distinct()
        )
        permissions = [row[0] for row in permissions_result.all()]

        return {
            "roles": roles,
            "permissions": permissions,
        }

    async def get_user_context(self, user_id: UUID) -> Dict[str, Any]:
        """Public helper to retrieve full impersonation context for a user."""
        user = await self._get_user_or_404(user_id)
        return await self._build_context_from_user(user)

    async def _build_context_from_user(self, user: Users) -> Dict[str, Any]:
        """Build impersonation-friendly context for a user."""
        auth_context = await self._get_auth_context(user.id)

        return {
            "user_id": str(user.id),
            "email": user.email,
            "full_name": user.full_name,
            "display_name": user.display_name,
            "roles": auth_context["roles"],
            "permissions": auth_context["permissions"],
        }

    async def invalidate_session(self, session_id: str) -> bool:
        """
        Invalidate an impersonation session by session_id.
        Store invalidated session in database.

        Args:
            session_id: Unique session identifier from JWT token

        Returns:
            bool: True if successfully invalidated, False otherwise
        """
        try:
            invalidated_session = ImpersonationSession(
                session_id=session_id, invalidated_at=datetime.now(timezone.utc), is_valid=False
            )
            self.db.add(invalidated_session)
            await self.db.flush()

            logger.info("Session invalidated successfully", extra={"session_id": session_id})
            return True
        except Exception as e:
            logger.error(f"Failed to invalidate session: {e}", extra={"session_id": session_id})
            return False

    async def is_session_valid(self, session_id: str) -> bool:
        """
        Check if a session_id is still valid (not invalidated).

        Args:
            session_id: Unique session identifier from JWT token

        Returns:
            bool: True if session is valid (not in invalidated table), False if invalidated
        """
        try:
            stmt = select(ImpersonationSession).where(
                ImpersonationSession.session_id == session_id,
                ImpersonationSession.is_valid.is_(False),
            )
            result = await self.db.execute(stmt)
            invalidated_session = result.scalar_one_or_none()

            # If found in invalidated table → invalid
            is_valid = invalidated_session is None

            logger.debug(
                "Session validity checked", extra={"session_id": session_id, "is_valid": is_valid}
            )

            return is_valid
        except Exception as e:
            logger.error(f"Failed to check session validity: {e}", extra={"session_id": session_id})
            # Fail closed for security
            return False
