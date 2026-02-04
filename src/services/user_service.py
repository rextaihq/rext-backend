"""
User Service - Business Logic for User Operations

This service encapsulates all business logic related to user management,
including profile operations, password management, and account status.

Responsibilities:
- User profile CRUD operations
- Password change and reset logic
- Account activation/deactivation
- User retrieval and validation

Does NOT:
- Handle HTTP requests/responses (that's routes)
- Commit transactions (that's decorators/routes)
- Authentication/authorization (that's decorators)
"""

from typing import Optional, Dict, Any, List
from uuid import UUID
from datetime import datetime, timezone
import bcrypt

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.models.user_models.users import Users
from src.utils.logger import logger
from src.api.middleware.exceptions import (
    ResourceNotFoundException,
    RextValidationException,
    DuplicateResourceException
)
from src.utils.account_cleanup import delete_deactivated_accounts, get_pending_deletions
from src.utils.token_cleanup import cleanup_expired_tokens


class UserService:
    """Service for user business logic"""

    def __init__(self, db: AsyncSession):
        """
        Initialize UserService.

        Args:
            db: Async database session
        """
        self.db = db

    async def get_user_by_id(
        self,
        user_id: UUID
    ) -> Users:
        """
        Get user by ID.

        Args:
            user_id: User UUID

        Returns:
            Users object

        Raises:
            ResourceNotFoundException: If user not found
        """
        result = await self.db.execute(
            select(Users).where(Users.id == user_id)
        )
        user = result.scalar_one_or_none()

        if not user:
            raise ResourceNotFoundException(
                resource_type="User",
                resource_id=str(user_id)
            )

        return user

    async def get_user_by_email(
        self,
        email: str
    ) -> Optional[Users]:
        """
        Get user by email.

        Args:
            email: User email address

        Returns:
            Users object or None if not found
        """
        result = await self.db.execute(
            select(Users).where(Users.email == email)
        )
        return result.scalar_one_or_none()

    async def update_profile(
        self,
        user_id: UUID,
        **kwargs
    ) -> Users:
        """
        Update user profile information.

        Args:
            user_id: User UUID
            **kwargs: Fields to update (full_name, display_name, bio,
                     avatar_url, language, timezone)

        Returns:
            Updated Users object

        Raises:
            ResourceNotFoundException: If user not found
            RextValidationException: If validation fails
        """
        user = await self.get_user_by_id(user_id)

        # Update only explicitly provided fields
        if "full_name" in kwargs:
            user.full_name = kwargs["full_name"]

        if "display_name" in kwargs:
            user.display_name = kwargs["display_name"]

        if "bio" in kwargs:
            # Validate bio length at service layer
            bio = kwargs["bio"]
            if bio is not None and len(bio) > 500:
                raise RextValidationException("Bio must be 500 characters or less")
            user.bio = bio

        if "avatar_url" in kwargs:
            # Allow setting to None to clear avatar
            user.avatar_url = kwargs["avatar_url"]

        if "language" in kwargs:
            user.language = kwargs["language"]

        if "timezone" in kwargs:
            user.timezone = kwargs["timezone"]

        user.updated_at = datetime.utcnow()

        logger.info(
            f"User profile updated: {user_id}",
            extra={"user_id": str(user_id), "updated_fields": list(kwargs.keys())}
        )

        return user

    async def change_password(
        self,
        user_id: UUID,
        current_password: str,
        new_password: str
    ) -> Users:
        """
        Change user password.

        Business Rules:
        - Current password must be correct
        - New password must be different from current
        - Updates password_changed_at timestamp

        Args:
            user_id: User UUID
            current_password: Current password (plain text)
            new_password: New password (plain text)

        Returns:
            Updated Users object

        Raises:
            ResourceNotFoundException: If user not found
            RextValidationException: If current password incorrect or passwords same
        """
        user = await self.get_user_by_id(user_id)

        # Verify current password
        if not bcrypt.checkpw(current_password.encode('utf-8'), user.password_hash.encode('utf-8')):
            raise RextValidationException(
                message="Current password is incorrect",
                field_errors={"current_password": ["Incorrect password"]}
            )

        # Ensure new password is different
        if bcrypt.checkpw(new_password.encode('utf-8'), user.password_hash.encode('utf-8')):
            raise RextValidationException(
                message="New password must be different from current password",
                field_errors={"new_password": ["Password must be different"]}
            )

        # Hash new password
        new_hash = bcrypt.hashpw(new_password.encode('utf-8'), bcrypt.gensalt())
        user.password_hash = new_hash.decode('utf-8')
        user.password_changed_at = datetime.utcnow()
        user.updated_at = datetime.utcnow()

        logger.info(
            f"User password changed: {user_id}",
            extra={"user_id": str(user_id)}
        )

        return user

    async def deactivate_account(
        self,
        user_id: UUID
    ) -> Users:
        """
        Deactivate user account.

        Sets status to 'inactive' and records deactivation timestamp.

        Args:
            user_id: User UUID

        Returns:
            Updated Users object

        Raises:
            ResourceNotFoundException: If user not found
        """
        user = await self.get_user_by_id(user_id)

        user.status = "inactive"
        user.deactivated_at = datetime.utcnow()
        user.updated_at = datetime.utcnow()

        logger.info(
            f"User account deactivated: {user_id}",
            extra={"user_id": str(user_id)}
        )

        return user

    async def reactivate_account(
        self,
        user_id: UUID
    ) -> Users:
        """
        Reactivate user account.

        Sets status to 'active' and clears deactivation timestamp.

        Args:
            user_id: User UUID

        Returns:
            Updated Users object

        Raises:
            ResourceNotFoundException: If user not found
        """
        user = await self.get_user_by_id(user_id)

        user.status = "active"
        user.deactivated_at = None
        user.updated_at = datetime.utcnow()

        logger.info(
            f"User account reactivated: {user_id}",
            extra={"user_id": str(user_id)}
        )

        return user

    async def cleanup_deactivated_accounts(self) -> int:
        """Permanently delete accounts deactivated for 14 or more days."""
        return delete_deactivated_accounts(self.db.sync_session)

    async def get_pending_deletions(self) -> list:
        """Return accounts scheduled for deletion."""
        return get_pending_deletions(self.db.sync_session)

    async def cleanup_expired_tokens(self) -> int:
        """Remove expired tokens from the blacklist."""
        return cleanup_expired_tokens(self.db.sync_session)

    async def update_last_login(
        self,
        user_id: UUID
    ) -> None:
        """
        Update user's last login timestamp and increment login count.

        Args:
            user_id: User UUID

        Raises:
            ResourceNotFoundException: If user not found
        """
        user = await self.get_user_by_id(user_id)

        user.last_login_at = datetime.utcnow()
        user.login_count = (user.login_count or 0) + 1
        user.failed_login_attempts = 0  # Reset failed attempts on successful login

        logger.info(
            f"User last login updated: {user_id}",
            extra={"user_id": str(user_id), "login_count": user.login_count}
        )

    async def get_users(
        self,
        workspace_id: Optional[UUID] = None,
        page: int = 1,
        per_page: int = 50,
    ) -> Dict[str, Any]:
        """
        Get paginated list of users, optionally filtered by workspace membership.

        Args:
            workspace_id: Optional workspace ID to filter by
            page: Page number (1-indexed)
            per_page: Items per page

        Returns:
            Dict with users list and pagination metadata
        """
        from src.api.models.workspace_models.workspace_member import WorkspaceMembers
        from sqlalchemy import func

        base_query = select(Users)

        if workspace_id:
            base_query = base_query.join(WorkspaceMembers).where(
                WorkspaceMembers.workspace_id == workspace_id,
                WorkspaceMembers.status == "active"
            )
            logger.info(f"Fetching users for workspace: {workspace_id}")
        else:
            logger.info("Fetching all users")

        # Get total count
        count_query = select(func.count()).select_from(base_query.subquery())
        count_result = await self.db.execute(count_query)
        total = count_result.scalar() or 0

        # Apply pagination
        offset = (page - 1) * per_page
        paginated_query = base_query.offset(offset).limit(per_page)
        result = await self.db.execute(paginated_query)
        users = list(result.scalars().all())

        total_pages = (total + per_page - 1) // per_page if total > 0 else 0

        logger.info(f"Retrieved {len(users)} users (page {page}/{total_pages})")
        return {
            "users": users,
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": total,
                "total_pages": total_pages,
                "has_next": page < total_pages,
                "has_prev": page > 1,
            },
        }

    async def delete_user(
        self,
        user_id: UUID
    ) -> Users:
        """
        Soft delete a user by setting deleted_at timestamp.

        Args:
            user_id: User UUID to delete

        Returns:
            Deleted user object

        Raises:
            ResourceNotFoundException: If user not found
            RextValidationException: If user already deleted
        """
        from src.api.middleware.exceptions import RextValidationException

        user = await self.get_user_by_id(user_id)

        if user.deleted_at:
            raise RextValidationException("User already deleted")

        user.deleted_at = datetime.utcnow()

        logger.info(f"User {user_id} soft deleted")
        return user

    async def check_user_permission(
        self,
        user_id: UUID,
        permission_name: str
    ) -> bool:
        """
        Check if user has a specific permission.

        Args:
            user_id: User UUID
            permission_name: Permission name (e.g., "user.delete")

        Returns:
            True if user has permission, False otherwise
        """
        from src.api.models.user_models.permissions import Permission
        from src.api.models.user_models.role_permissions import RolePermission
        from src.api.models.user_models.user_roles import UserRole

        query = select(Permission).join(
            RolePermission, RolePermission.permission_id == Permission.id
        ).join(
            UserRole, UserRole.role_id == RolePermission.role_id
        ).where(
            UserRole.user_id == user_id,
            Permission.name == permission_name
        )

        result = await self.db.execute(query)
        permission = result.scalar_one_or_none()

        has_permission = permission is not None
        logger.debug(f"Permission check for user {user_id}, permission '{permission_name}': {has_permission}")

        return has_permission

    async def update_user(
        self,
        user_id: UUID,
        email: Optional[str] = None,
        full_name: Optional[str] = None,
        display_name: Optional[str] = None,
        language: Optional[str] = None,
        timezone: Optional[str] = None
    ) -> Users:
        """
        Update user with email validation and profile fields.

        Args:
            user_id: User UUID
            email: New email (will check for duplicates)
            full_name: Full name
            display_name: Display name
            language: Language preference
            timezone: Timezone preference

        Returns:
            Updated user object

        Raises:
            ResourceNotFoundException: If user not found
            RextValidationException: If email already exists
        """
        from src.api.middleware.exceptions import RextValidationException

        user = await self.get_user_by_id(user_id)

        # Check for duplicate email
        if email and email != user.email:
            query = select(Users).where(
                Users.email == email,
                Users.id != user_id
            )
            result = await self.db.execute(query)
            if result.scalar_one_or_none():
                raise RextValidationException("Email already exists")
            user.email = email

        # Update profile fields
        if full_name is not None:
            user.full_name = full_name
        if display_name is not None:
            user.display_name = display_name
        if language is not None:
            user.language = language
        if timezone is not None:
            user.timezone = timezone

        user.updated_at = datetime.utcnow()

        logger.info(f"User {user_id} updated successfully")
        return user

    async def set_reset_token(
        self,
        user_id: UUID,
        reset_token: str
    ) -> Users:
        """
        Set password reset token for user.

        Args:
            user_id: User UUID
            reset_token: Password reset token

        Returns:
            User object with updated reset_token

        Raises:
            ResourceNotFoundException: If user not found
        """
        user = await self.get_user_by_id(user_id)
        user.reset_token = reset_token

        logger.info(f"Reset token set for user {user_id}")
        return user

    async def reset_password_with_token(
        self,
        reset_token: str,
        new_password: str
    ) -> Users:
        """
        Reset user password using reset token.

        Args:
            reset_token: Password reset token
            new_password: New password to set

        Returns:
            User object with updated password

        Raises:
            ResourceNotFoundException: If no user found with that token
        """
        from src.api.security.token_utils import hash_password

        # Find user by reset token
        query = select(Users).where(Users.reset_token == reset_token)
        result = await self.db.execute(query)
        user = result.scalar_one_or_none()

        if not user:
            raise ResourceNotFoundException("Invalid or expired reset token")

        # Update password
        user.password_hash = hash_password(new_password)
        user.reset_token = None
        user.password_changed_at = datetime.utcnow()

        logger.info(f"Password reset successfully for user {user.id}")
        return user

    async def verify_user_password(
        self,
        user_id: UUID,
        password: str
    ) -> bool:
        """
        Verify user's password.

        Args:
            user_id: User UUID
            password: Password to verify

        Returns:
            True if password is correct, False otherwise

        Raises:
            ResourceNotFoundException: If user not found
        """
        from src.api.security.token_utils import verify_password

        user = await self.get_user_by_id(user_id)

        is_valid = verify_password(password, user.password_hash)
        logger.debug(f"Password verification for user {user_id}: {is_valid}")

        return is_valid

    async def get_user_by_email_or_404(
        self,
        email: str,
        exclude_deleted: bool = True
    ) -> Users:
        """
        Get user by email or raise 404.

        Args:
            email: User email address
            exclude_deleted: Whether to exclude soft-deleted users

        Returns:
            User object

        Raises:
            ResourceNotFoundException: If user not found
        """
        query = select(Users).where(Users.email == email.lower())

        if exclude_deleted:
            query = query.where(Users.deleted_at.is_(None))

        result = await self.db.execute(query)
        user = result.scalar_one_or_none()

        if not user:
            raise ResourceNotFoundException(
                resource_type="user",
                resource_id=email
            )

        logger.debug(f"Found user by email: {email}")
        return user

    async def get_users_by_ids(
        self,
        user_ids: list[UUID]
    ) -> Dict[UUID, Users]:
        """
        Batch load users by IDs.

        Args:
            user_ids: List of user UUIDs

        Returns:
            Dict mapping user_id -> Users object
        """
        if not user_ids:
            return {}

        result = await self.db.execute(
            select(Users).where(Users.id.in_(user_ids))
        )
        users = result.scalars().all()

        return {user.id: user for user in users}
