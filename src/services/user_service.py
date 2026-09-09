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

from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import UUID

import bcrypt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.api.middleware.exceptions import (
    ResourceNotFoundException,
    RextValidationException,
)
from src.api.models.user_models.users import Users
from src.utils.account_cleanup import delete_deactivated_accounts, get_pending_deletions
from src.utils.logger import logger
from src.utils.password_utils import validate_password_strength
from src.utils.token_cleanup import cleanup_expired_tokens

# Distinguishes "field omitted" from "field explicitly set to null", so an
# admin clearing the avatar actually clears it instead of being ignored.
_UNSET: Any = object()


class UserService:
    """Service for user business logic"""

    def __init__(self, db: AsyncSession):
        """
        Initialize UserService.

        Args:
            db: Async database session
        """
        self.db = db

    async def get_user_by_id(self, user_id: UUID) -> Users:
        """
        Get user by ID.

        Args:
            user_id: User UUID

        Returns:
            Users object

        Raises:
            ResourceNotFoundException: If user not found
        """
        from sqlalchemy.orm import selectinload

        from src.api.models.user_models.user_roles import UserRole

        result = await self.db.execute(
            select(Users)
            .options(
                selectinload(Users.user_roles).selectinload(UserRole.role),
                selectinload(Users.user_roles).selectinload(UserRole.workspace),
            )
            .where(Users.id == user_id)
        )
        user = result.scalar_one_or_none()

        if not user:
            raise ResourceNotFoundException(resource_type="User", resource_id=str(user_id))

        return user

    async def get_user_by_email(self, email: str) -> Optional[Users]:
        """
        Get user by email.

        Args:
            email: User email address

        Returns:
            Users object or None if not found
        """
        result = await self.db.execute(select(Users).where(Users.email == email))
        return result.scalar_one_or_none()

    async def update_profile(self, user_id: UUID, **kwargs) -> Users:
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

        user.updated_at = datetime.now(timezone.utc)

        logger.info(
            f"User profile updated: {user_id}",
            extra={"user_id": str(user_id), "updated_fields": list(kwargs.keys())},
        )
        self.db.add(user)
        await self.db.commit()
        return user

    async def change_password(
        self, user_id: UUID, current_password: str, new_password: str
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
        from src.api.security.token_utils import verify_password

        user = await self.get_user_by_id(user_id)

        # Handle OAuth users who don't have a password set
        if user.password_hash is None:
            raise RextValidationException(
                message="Your account does not have a password set (OAuth-only). Please use the password reset flow to set a password for the first time.",
                field_errors={"current_password": ["No password set for this account"]},
            )

        # Verify current password
        if not verify_password(current_password, user.password_hash):
            raise RextValidationException(
                message="Current password is incorrect",
                field_errors={"current_password": ["Incorrect password"]},
            )

        # Ensure new password is different
        if verify_password(new_password, user.password_hash):
            raise RextValidationException(
                message="New password must be different from current password",
                field_errors={"new_password": ["Password must be different"]},
            )

        # Validate new password strength
        validate_password_strength(new_password)

        # Hash new password
        new_hash = bcrypt.hashpw(new_password.encode("utf-8"), bcrypt.gensalt())
        user.password_hash = new_hash.decode("utf-8")
        user.password_changed_at = datetime.now(timezone.utc)
        user.updated_at = datetime.now(timezone.utc)

        logger.info(f"User password changed: {user_id}", extra={"user_id": str(user_id)})
        self.db.add(user)
        await self.db.commit()
        return user

    async def deactivate_account(self, user_id: UUID) -> Users:
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
        user.deactivated_at = datetime.now(timezone.utc)
        user.updated_at = datetime.now(timezone.utc)

        logger.info(f"User account deactivated: {user_id}", extra={"user_id": str(user_id)})
        self.db.add(user)
        # Flush only — the caller's transaction handler owns the commit
        await self.db.flush()
        return user

    async def reactivate_account(self, user_id: UUID) -> Users:
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
        user.updated_at = datetime.now(timezone.utc)

        logger.info(f"User account reactivated: {user_id}", extra={"user_id": str(user_id)})
        self.db.add(user)
        # Flush only — the caller's transaction handler owns the commit
        await self.db.flush()
        return user

    async def change_user_status(
        self,
        user_id: UUID,
        new_status: str,
    ) -> tuple[Users, str]:
        """
        Change a user's status to a specified value.

        Validates that the new status is one of the allowed values,
        fetches the user, records the old status, and updates.

        Args:
            user_id: User UUID
            new_status: New status value (e.g., "suspended", "banned", "active", "inactive")

        Returns:
            Tuple of (updated Users object, old_status string)

        Raises:
            ResourceNotFoundException: If user not found
            RextValidationException: If new_status is not a valid status
        """
        valid_statuses = {"active", "inactive", "suspended", "banned"}
        if new_status not in valid_statuses:
            raise RextValidationException(
                message=f"Invalid status: {new_status}. Must be one of: {', '.join(sorted(valid_statuses))}"
            )

        user = await self.get_user_by_id(user_id)
        old_status = user.status

        user.status = new_status
        if new_status == "active":
            user.deactivated_at = None
        user.updated_at = datetime.now(timezone.utc)

        logger.info(
            f"User status changed: {user_id} ({old_status} -> {new_status})",
            extra={
                "user_id": str(user_id),
                "old_status": old_status,
                "new_status": new_status,
            },
        )
        self.db.add(user)
        await self.db.commit()
        return user, old_status

    async def cleanup_deactivated_accounts(self) -> int:
        """
        Permanently delete accounts deactivated for 14 or more days.

        Returns:
            Number of accounts deleted
        """
        return await delete_deactivated_accounts(self.db)

    async def get_pending_deletions(self) -> list:
        """
        Return accounts scheduled for deletion.

        Returns:
            List of user dictionaries with deletion information
        """
        return await get_pending_deletions(self.db)

    async def cleanup_expired_tokens(self) -> int:
        """
        Remove expired tokens from the blacklist.

        Returns:
            Number of tokens cleaned up
        """
        return await cleanup_expired_tokens(self.db)

    async def update_last_login(self, user_id: UUID) -> None:
        """
        Update user's last login timestamp and increment login count.

        Args:
            user_id: User UUID

        Raises:
            ResourceNotFoundException: If user not found
        """
        user = await self.get_user_by_id(user_id)

        user.last_login_at = datetime.now(timezone.utc)
        user.login_count = (user.login_count or 0) + 1
        user.failed_login_attempts = 0  # Reset failed attempts on successful login

        self.db.add(user)
        await self.db.commit()
        logger.info(
            f"User last login updated: {user_id}",
            extra={"user_id": str(user_id), "login_count": user.login_count},
        )

    # Whitelisted sort columns. Resolving with getattr(Users, sort_by) would
    # accept properties like `initials` (order_by then raises) and would make
    # password_hash a legal ordering key.
    SORTABLE_FIELDS = {
        "created_at": Users.created_at,
        "updated_at": Users.updated_at,
        "email": Users.email,
        "full_name": Users.full_name,
        "display_name": Users.display_name,
        "status": Users.status,
        "last_login_at": Users.last_login_at,
        "login_count": Users.login_count,
    }

    async def get_user_stats(self) -> Dict[str, int]:
        """
        Aggregate user counts in a single query.

        Backs the User Management stat cards. Previously these were derived in
        the browser from a full download of every user; counting server-side
        keeps them correct now that the table is paginated. Soft-deleted
        accounts are excluded, matching get_users().
        """
        from sqlalchemy import case, func

        def count_where(condition):
            return func.count(case((condition, 1)))

        result = await self.db.execute(
            select(
                func.count(Users.id).label("total"),
                count_where(Users.status == "active").label("active"),
                count_where(Users.status == "inactive").label("inactive"),
                count_where(Users.status == "suspended").label("suspended"),
                count_where(Users.status == "banned").label("banned"),
                count_where(Users.email_verified.is_(True)).label("verified"),
                count_where(Users.email_verified.is_(False)).label("unverified"),
            ).where(Users.deleted_at.is_(None))
        )
        row = result.one()

        return {
            "total": row.total or 0,
            "active": row.active or 0,
            "inactive": row.inactive or 0,
            "suspended": row.suspended or 0,
            "banned": row.banned or 0,
            "verified": row.verified or 0,
            "unverified": row.unverified or 0,
        }

    async def get_users(
        self,
        workspace_id: Optional[UUID] = None,
        page: int = 1,
        per_page: int = 50,
        include_deleted: bool = False,
        search: Optional[str] = None,
        status: Optional[str] = None,
        role: Optional[str] = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ) -> Dict[str, Any]:
        """
        Get paginated list of users, optionally filtered by workspace membership,
        search term, account status, and dynamic sorting. Soft-deleted users are excluded.

        Args:
            workspace_id: Optional workspace ID to filter by
            page: Page number (1-indexed)
            per_page: Items per page
            include_deleted: Include soft-deleted accounts (default False)
            search: Optional search string (matches email, full_name, display_name)
            status: Optional account status (active, inactive, suspended, banned)
            role: Optional role name or display name the user must hold
            sort_by: Column name to sort by (must be in SORTABLE_FIELDS)
            sort_order: 'asc' or 'desc'

        Returns:
            Dict with users list and pagination metadata
        """
        from sqlalchemy import asc, desc, func, or_

        from src.api.models.user_models.roles import Role
        from src.api.models.user_models.user_roles import UserRole
        from src.api.models.workspace_models.workspace_member import WorkspaceMembers

        base_query = select(Users).options(
            selectinload(Users.user_roles).selectinload(UserRole.role),
            selectinload(Users.user_roles).selectinload(UserRole.workspace),
        )

        if not include_deleted:
            base_query = base_query.where(Users.deleted_at.is_(None))

        if workspace_id:
            base_query = base_query.join(WorkspaceMembers).where(
                WorkspaceMembers.workspace_id == workspace_id, WorkspaceMembers.status == "active"
            )
            logger.info(f"Fetching users for workspace: {workspace_id}")
        else:
            logger.info("Fetching all users")

        if status:
            if status == "pending":
                base_query = base_query.where(
                    Users.email_verified.is_(False),
                )
            else:
                base_query = base_query.where(Users.status == status)

        if search and search.strip():
            search_pattern = f"%{search.strip()}%"
            base_query = base_query.where(
                or_(
                    Users.email.ilike(search_pattern),
                    Users.full_name.ilike(search_pattern),
                    Users.display_name.ilike(search_pattern),
                )
            )

        if role and role.strip():
            # Matched as an EXISTS rather than a join so a user holding the
            # same role in several scopes is not returned more than once.
            role_term = role.strip()
            base_query = base_query.where(
                select(UserRole.id)
                .join(Role, Role.id == UserRole.role_id)
                .where(
                    UserRole.user_id == Users.id,
                    or_(Role.name == role_term, Role.display_name == role_term),
                )
                .exists()
            )

        # Dynamic sorting, restricted to a known-safe set of columns.
        sort_attr = self.SORTABLE_FIELDS.get(sort_by)
        order_func = desc if sort_order.lower() == "desc" else asc
        if sort_attr is not None:
            base_query = base_query.order_by(order_func(sort_attr))
        else:
            base_query = base_query.order_by(desc(Users.created_at))

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

    async def delete_user(self, user_id: UUID) -> Users:
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
        from sqlalchemy import delete

        from src.api.middleware.exceptions import RextValidationException
        from src.api.models.user_models.user_sessions import UserSession

        user = await self.get_user_by_id(user_id)

        if user.is_deleted:
            raise RextValidationException("User already deleted")

        user.status = "inactive"
        user.deleted_at = datetime.now(timezone.utc)

        # Invalidate all user sessions to immediately revoke active access tokens
        await self.db.execute(delete(UserSession).where(UserSession.user_id == user_id))

        logger.info(f"User {user_id} soft deleted and sessions revoked")
        return user

    async def check_user_permission(self, user_id: UUID, permission_name: str) -> bool:
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

        query = (
            select(Permission)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .join(UserRole, UserRole.role_id == RolePermission.role_id)
            .where(UserRole.user_id == user_id, Permission.name == permission_name)
        )

        result = await self.db.execute(query)
        permission = result.scalar_one_or_none()

        has_permission = permission is not None
        logger.debug(
            f"Permission check for user {user_id}, permission '{permission_name}': {has_permission}"
        )

        return has_permission

    async def update_user(
        self,
        user_id: UUID,
        email: Optional[str] = None,
        full_name: Optional[str] = None,
        display_name: Optional[str] = None,
        language: Optional[str] = None,
        timezone: Optional[str] = None,
        password: Optional[str] = None,
        avatar_url: Optional[str] = _UNSET,
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
            password: New password (will be hashed)
            avatar_url: Profile avatar URL

        Returns:
            Updated user object

        Raises:
            ResourceNotFoundException: If user not found
            RextValidationException: If email already exists
        """
        # The `timezone` parameter above shadows datetime.timezone inside this
        # function, so the module-level import cannot be used here.
        from datetime import timezone as dt_timezone

        from src.api.middleware.exceptions import RextValidationException
        from src.api.security.token_utils import hash_password

        user = await self.get_user_by_id(user_id)

        # Check for duplicate email
        if email and email != user.email:
            query = select(Users).where(Users.email == email, Users.id != user_id)
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
        # Explicit null clears the avatar; omitted leaves it untouched.
        if avatar_url is not _UNSET:
            user.avatar_url = avatar_url

        # Handle password update
        if password:
            validate_password_strength(password)
            user.password_hash = hash_password(password)
            user.password_changed_at = datetime.now(dt_timezone.utc)

        user.updated_at = datetime.now(dt_timezone.utc)

        logger.info(f"User {user_id} updated successfully")

        self.db.add(user)
        await self.db.commit()
        return user

    async def set_reset_token(self, user_id: UUID, reset_token: str) -> Users:
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

        self.db.add(user)
        await self.db.commit()
        return user

    async def reset_password_with_token(self, reset_token: str, new_password: str) -> Users:
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

        # Validate new password strength
        validate_password_strength(new_password)

        # Update password
        user.password_hash = hash_password(new_password)
        user.reset_token = None
        user.password_changed_at = datetime.now(timezone.utc)

        logger.info(f"Password reset successfully for user {user.id}")
        self.db.add(user)
        await self.db.commit()
        return user

    async def verify_user_password(self, user_id: UUID, password: str) -> bool:
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

        if user.password_hash is None:
            return False

        is_valid = verify_password(password, user.password_hash)
        logger.debug(f"Password verification for user {user_id}: {is_valid}")

        return is_valid

    async def get_user_by_email_or_404(self, email: str, exclude_deleted: bool = True) -> Users:
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
            query = query.where(Users.active())

        result = await self.db.execute(query)
        user = result.scalar_one_or_none()

        if not user:
            raise ResourceNotFoundException(resource_type="user", resource_id=email)

        logger.debug(f"Found user by email: {email}")
        return user

    async def get_users_by_ids(self, user_ids: list[UUID]) -> Dict[UUID, Users]:
        """
        Batch load users by IDs.

        Args:
            user_ids: List of user UUIDs

        Returns:
            Dict mapping user_id -> Users object
        """
        if not user_ids:
            return {}

        result = await self.db.execute(select(Users).where(Users.id.in_(user_ids)))
        users = result.scalars().all()

        return {user.id: user for user in users}

    async def request_account_recovery(self, email: str) -> tuple[Users, str]:
        """
        Generate a recovery token for an account inside its retention window.

        Covers both states an account can be waiting in:
        - soft-deleted (deleted_at set) — deleted by an admin or by cleanup
        - self-deactivated (status "inactive", deactivated_at set, deleted_at
          NULL) — reactivating one requires confirming ownership by email, so
          the same token flow serves it.

        Args:
            email: User email address

        Returns:
            Tuple of (Users, recovery_token)

        Raises:
            ResourceNotFoundException: If user not found
            RextValidationException: If account not soft-deleted or retention expired
        """
        from datetime import timedelta

        from src.api.config import get_settings
        from src.api.security.token_utils import create_recovery_token

        settings = get_settings()

        # Get user, including soft-deleted ones
        result = await self.db.execute(select(Users).where(Users.email == email.lower()))
        user = result.scalar_one_or_none()

        if not user:
            raise ResourceNotFoundException(resource_type="user", resource_id=email)

        # Whichever timestamp started the retention clock is the one to
        # measure the deadline against.
        retention_started_at = user.deleted_at or user.deactivated_at
        is_recoverable = user.is_deleted or user.status == "inactive"

        if not is_recoverable or not retention_started_at:
            raise RextValidationException(
                "This account is currently active and does not require recovery."
            )

        # Check retention period enforcement
        retention_days = settings.USER_DELETION_RETENTION_DAYS
        restore_deadline = retention_started_at + timedelta(days=retention_days)

        if datetime.now(timezone.utc) >= restore_deadline:
            raise RextValidationException(
                "Account recovery period has expired. The account is scheduled for permanent deletion."
            )

        # Generate short-lived recovery token
        recovery_token = create_recovery_token({"id": str(user.id), "email": user.email})

        logger.info(f"Account recovery requested for user {user.id}")
        return user, recovery_token

    async def verify_account_recovery(self, token: str) -> Users:
        """
        Verify a recovery token, ensure it is single-use, and restore the account if valid.

        Args:
            token: Recovery JWT token

        Returns:
            Restored Users object

        Raises:
            RextAuthenticationException: If token is invalid or expired
            RextValidationException: If token is already used or retention expired
        """
        from datetime import timedelta

        from src.api.config import get_settings
        from src.api.middleware.exceptions import RextAuthenticationException
        from src.api.models.user_models.token_blacklist import TokenBlacklist
        from src.api.security.token_utils import (
            blacklist_token_in_cache,
            decode_and_verify_token,
            is_token_blacklisted,
        )

        settings = get_settings()

        # Decode token and verify signature (also checks 'exp' and type="account_recovery")
        payload = decode_and_verify_token(token, expected_type="account_recovery")

        jti = payload.get("jti")
        user_id = payload.get("id")
        exp = payload.get("exp")

        if not jti or not user_id:
            raise RextAuthenticationException(message="Invalid recovery token payload")

        # Ensure single-use via TokenBlacklist
        if await is_token_blacklisted(jti, self.db):
            raise RextValidationException("This recovery link has already been used.")

        user = await self.get_user_by_id(UUID(str(user_id)))

        retention_started_at = user.deleted_at or user.deactivated_at

        if (not user.is_deleted and user.status != "inactive") or not retention_started_at:
            raise RextValidationException("Account is already active.")

        # Re-verify retention period enforcement at verification time
        retention_days = settings.USER_DELETION_RETENTION_DAYS
        restore_deadline = retention_started_at + timedelta(days=retention_days)

        if datetime.now(timezone.utc) >= restore_deadline:
            raise RextValidationException(
                "Account recovery period has expired. The account is scheduled for permanent deletion."
            )

        # Blacklist the token immediately to prevent replay
        # Use timezone-aware conversion for exp timestamp
        exp_dt = datetime.fromtimestamp(exp, tz=timezone.utc)

        blacklist_entry = TokenBlacklist(
            jti=jti,
            token_type="recovery",
            user_id=user.id,
            expires_at=exp_dt,
            reason="account_recovered",
        )
        self.db.add(blacklist_entry)

        # Also cache it in Redis for immediate distributed blocking
        await blacklist_token_in_cache(jti, exp)

        # Restore the user. Clear both markers so neither the deletion
        # cleanup job nor the login deactivation check picks it up again.
        user.status = "active"
        user.deleted_at = None
        user.deactivated_at = None
        user.updated_at = datetime.now(timezone.utc)

        self.db.add(user)
        # Flush is required because the route handler will commit the transaction
        await self.db.flush()

        logger.info(f"Account restored successfully for user {user.id}")
        return user
