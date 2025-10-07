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

from typing import Optional, Dict, Any
from uuid import UUID
from datetime import datetime, timezone
import bcrypt

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.models.user_models.users import Users
from src.utils.logger import logger
from src.api.middleware.exceptions import (
    ResourceNotFoundException,
    WrextValidationException,
    DuplicateResourceException
)


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
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        display_name: Optional[str] = None,
        avatar_url: Optional[str] = None,
        language: Optional[str] = None,
        timezone: Optional[str] = None
    ) -> Users:
        """
        Update user profile information.

        Args:
            user_id: User UUID
            first_name: First name
            last_name: Last name
            display_name: Display name
            avatar_url: Avatar URL
            language: Language preference
            timezone: Timezone preference

        Returns:
            Updated Users object

        Raises:
            ResourceNotFoundException: If user not found
        """
        user = await self.get_user_by_id(user_id)

        # Update only provided fields
        if first_name is not None:
            user.first_name = first_name

        if last_name is not None:
            user.last_name = last_name

        if display_name is not None:
            user.display_name = display_name

        if avatar_url is not None:
            user.avatar_url = avatar_url

        if language is not None:
            user.language = language

        if timezone is not None:
            user.timezone = timezone

        user.updated_at = datetime.utcnow()

        logger.info(
            f"User profile updated: {user_id}",
            extra={"user_id": str(user_id)}
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
            WrextValidationException: If current password incorrect or passwords same
        """
        user = await self.get_user_by_id(user_id)

        # Verify current password
        if not bcrypt.checkpw(current_password.encode('utf-8'), user.password_hash.encode('utf-8')):
            raise WrextValidationException(
                message="Current password is incorrect",
                field_errors={"current_password": ["Incorrect password"]}
            )

        # Ensure new password is different
        if bcrypt.checkpw(new_password.encode('utf-8'), user.password_hash.encode('utf-8')):
            raise WrextValidationException(
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
