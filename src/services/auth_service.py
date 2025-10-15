"""
Auth Service - Business Logic for Authentication Operations

This service encapsulates all business logic related to user authentication,
including registration, login, logout, token management, and password operations.

Responsibilities:
- User registration with role assignment
- Login with session tracking and failed attempt monitoring
- Email verification workflow
- Token refresh and rotation
- Logout with token blacklisting
- Password reset flow
- Account locking after failed attempts

Does NOT:
- Handle HTTP requests/responses (that's routes)
- Commit transactions (that's decorators/routes)
- Send emails directly (uses background tasks from routes)
"""

from typing import Tuple, Dict, Any, Optional
from uuid import UUID
from datetime import datetime, timedelta, timezone
import os

from sqlalchemy.orm import Session
from sqlalchemy import select

from src.api.models.user_models.users import Users
from src.api.models.user_models.roles import Role
from src.api.models.user_models.user_roles import UserRole
from src.api.models.user_models.permissions import Permission
from src.api.models.user_models.role_permissions import RolePermission
from src.api.models.user_models.token_blacklist import TokenBlacklist
from src.api.models.user_models.user_sessions import UserSession
from src.api.models.subscription_models.plans import SubscriptionPlan
from src.api.models.subscription_models.subscriptions import (
    UserSubscription,
    SubscriptionStatus,
    BillingPeriod
)
from src.api.security.token_utils import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    create_verification_token,
    verify_token,
    verify_refresh_token,
    is_token_blacklisted
)
from src.utils.logger import logger
from src.api.middleware.exceptions import (
    DuplicateResourceException,
    WrextAuthenticationException,
    ResourceNotFoundException
)


class AuthService:
    """Service for authentication business logic"""

    def __init__(self, db: Session):
        """
        Initialize AuthService.

        Args:
            db: Database session
        """
        self.db = db

    async def register_user(
        self,
        email: str,
        username: str,
        password: str,
        first_name: str,
        last_name: str
    ) -> Tuple[Users, str]:
        """
        Register new user with role assignment and trial subscription.

        Business Rules:
        - Email and username must be unique
        - Password is hashed before storage
        - Default 'user' role is assigned
        - Trial subscription is auto-assigned (14 days)
        - Verification token is generated (valid 24 hours)

        Args:
            email: User email
            username: Username
            password: Plain text password
            first_name: First name
            last_name: Last name

        Returns:
            Tuple of (User object, verification_token)

        Raises:
            DuplicateResourceException: If email or username exists
        """
        # Check if user exists
        existing_user = self.db.query(Users).filter(
            (Users.email == email) | (Users.username == username)
        ).first()

        if existing_user:
            if existing_user.email == email:
                raise DuplicateResourceException(
                    message="A user with this email already exists",
                    resource_type="user",
                    conflicting_field="email",
                    conflicting_value=email
                )
            else:
                raise DuplicateResourceException(
                    message="A user with this username already exists",
                    resource_type="user",
                    conflicting_field="username",
                    conflicting_value=username
                )

        # Hash password
        hashed_pwd = hash_password(password)

        # Create user
        new_user = Users(
            first_name=first_name,
            last_name=last_name,
            username=username,
            email=email,
            password_hash=hashed_pwd,
            created_at=datetime.utcnow()
        )
        self.db.add(new_user)
        self.db.flush()

        # Assign default role
        default_role = self._get_or_create_default_role()

        user_role = UserRole(
            user_id=new_user.id,
            role_id=default_role.id,
            workspace_id=None,
            is_primary=True,
            assigned_at=datetime.utcnow(),
            assigned_by_user_id=new_user.id
        )
        self.db.add(user_role)
        self.db.flush()

        # Create trial subscription (auto-assigned on signup)
        trial_plan = self._get_trial_plan()
        if trial_plan:
            trial_start = datetime.utcnow()
            trial_end = trial_start + timedelta(days=14)

            trial_subscription = UserSubscription(
                user_id=new_user.id,
                plan_id=trial_plan.id,
                status=SubscriptionStatus.TRIAL,  # Use TRIAL status for trial subscriptions
                billing_period=BillingPeriod.MONTHLY,
                start_date=trial_start,
                end_date=trial_end,
                trial_end_date=trial_end,
                created_at=trial_start,
                updated_at=trial_start
            )
            self.db.add(trial_subscription)
            self.db.flush()

            logger.info(
                f"Trial subscription created for user: {new_user.id}",
                extra={"plan_id": str(trial_plan.id), "trial_end": trial_end.isoformat()}
            )

        # Generate verification token
        verification_token = create_verification_token({"user_id": str(new_user.id)})

        logger.info(
            f"User registered: {new_user.id}",
            extra={"email": email, "username": username, "has_trial": trial_plan is not None}
        )

        return new_user, verification_token

    async def login_user(
        self,
        email: str,
        password: str,
        device_info: Dict[str, str]
    ) -> Tuple[Users, Dict[str, Any]]:
        """
        Authenticate user and create session.

        Business Rules:
        - Account is locked for 1 hour after 3 failed attempts
        - Failed attempts counter is reset on successful login
        - Session is created with device tracking
        - Tokens include user roles and permissions

        Args:
            email: User email
            password: Plain text password
            device_info: Dict with device_name, device_type, user_agent, ip_address

        Returns:
            Tuple of (User object, tokens dict with access_token, refresh_token, token_type)

        Raises:
            WrextAuthenticationException: If credentials invalid or account locked
        """
        # Find user
        db_user = self.db.query(Users).filter(Users.email == email).first()

        if not db_user:
            raise WrextAuthenticationException(
                message="Invalid email or password",
                context={"login_attempt": email}
            )

        # Check if account is locked
        if db_user.locked_until and db_user.locked_until > datetime.utcnow():
            raise WrextAuthenticationException(
                message="Account is temporarily locked due to multiple failed login attempts. Please try again later.",
                context={"locked_until": db_user.locked_until.isoformat()}
            )

        # Verify password
        is_match = verify_password(password=password, hashed_password=db_user.password_hash)

        if not is_match:
            # Increment failed attempts
            db_user.failed_login_attempts = (db_user.failed_login_attempts or 0) + 1

            # Lock account if too many failures (configurable via env vars)
            max_attempts = int(os.getenv("AUTH_MAX_LOGIN_ATTEMPTS", "3"))
            lockout_hours = int(os.getenv("AUTH_LOCKOUT_DURATION_HOURS", "1"))

            if db_user.failed_login_attempts >= max_attempts:
                db_user.locked_until = datetime.utcnow() + timedelta(hours=lockout_hours)

            self.db.flush()

            raise WrextAuthenticationException(
                message="Invalid email or password",
                context={"login_attempt": email}
            )

        # Successful login - reset failed attempts
        db_user.failed_login_attempts = 0
        db_user.last_login_at = datetime.utcnow()
        db_user.login_count = (db_user.login_count or 0) + 1
        self.db.flush()

        # Get roles and permissions
        role_names = [ur.role.name for ur in db_user.user_roles if ur.is_primary]

        permission_names = (
            self.db.query(Permission.name)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .join(UserRole, UserRole.role_id == RolePermission.role_id)
            .filter(UserRole.user_id == db_user.id)
            .filter(UserRole.workspace_id == None)  # Global permissions only
            .distinct()
            .all()
        )
        permissions = [p.name for p in permission_names]

        # Prepare token data
        token_data = {
            "id": str(db_user.id),
            "username": db_user.username,
            "email": db_user.email,
            "roles": role_names,
            "permissions": permissions
        }

        # Generate tokens
        access_token = create_access_token(data=token_data)
        refresh_token = create_refresh_token(data=token_data)

        # Create session
        access_payload = verify_token(access_token)
        jti = access_payload.get("jti")
        exp_timestamp = access_payload.get("exp")
        expires_at = datetime.utcfromtimestamp(exp_timestamp) if exp_timestamp else datetime.utcnow() + timedelta(hours=24)

        new_session = UserSession(
            user_id=db_user.id,
            jti=jti,
            device_name=device_info.get("device_name", "Unknown"),
            device_type=device_info.get("device_type", "desktop"),
            user_agent=device_info.get("user_agent", "Unknown"),
            ip_address=device_info.get("ip_address", "Unknown"),
            is_active=True,
            created_at=datetime.utcnow(),
            last_activity_at=datetime.utcnow(),
            expires_at=expires_at
        )
        self.db.add(new_session)
        self.db.flush()

        logger.info(
            f"User logged in: {db_user.id}",
            extra={"email": email, "session_id": str(new_session.id)}
        )

        tokens = {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "permissions": permissions,  # Include permissions for route response
            "roles": role_names  # Include roles for route response
        }

        return db_user, tokens

    async def verify_email(self, token: str) -> Users:
        """
        Verify user email using token.

        Args:
            token: Verification token

        Returns:
            User object

        Raises:
            WrextAuthenticationException: If token invalid or user not found
        """
        payload = verify_token(token)
        user_id = payload.get("user_id")

        if not user_id:
            raise WrextAuthenticationException(
                message="Invalid token payload",
                context={"error": "Missing user_id"}
            )

        user = self.db.query(Users).filter(Users.id == user_id).first()

        if not user:
            raise ResourceNotFoundException(
                resource_type="User",
                resource_id=user_id
            )

        if not user.email_verified:
            user.email_verified = True
            user.email_verified_at = datetime.utcnow()
            self.db.flush()

        logger.info(
            f"Email verified for user: {user_id}",
            extra={"email": user.email}
        )

        return user

    async def resend_verification_email(self, email: str) -> Tuple[Users, str]:
        """
        Resend email verification for a user.

        Business Rules:
        - User must exist
        - Email must not be already verified
        - Generates new verification token

        Args:
            email: User email address

        Returns:
            Tuple of (User object, new_verification_token)

        Raises:
            ResourceNotFoundException: If user not found
            WrextAuthenticationException: If email already verified
        """
        # Find user by email
        user = self.db.query(Users).filter(Users.email == email).first()

        if not user:
            raise ResourceNotFoundException(
                resource_type="User",
                resource_id=email
            )

        # Check if already verified
        if user.email_verified:
            raise WrextAuthenticationException(
                message="Email is already verified",
                context={"email": email}
            )

        # Generate new verification token
        verification_token = create_verification_token(
            data={"user_id": str(user.id)}
        )

        # Update user's verification token
        user.verification_token = verification_token
        self.db.flush()

        logger.info(
            f"Verification email resent for user: {user.id}",
            extra={"email": email}
        )

        return user, verification_token

    async def refresh_token(self, refresh_token: str) -> Dict[str, str]:
        """
        Generate new access token using refresh token.

        Implements token rotation - old refresh token is blacklisted.

        Args:
            refresh_token: Refresh token

        Returns:
            Dict with new access_token, refresh_token, token_type

        Raises:
            WrextAuthenticationException: If token invalid, blacklisted, or user not active
        """
        # Verify refresh token
        payload = verify_refresh_token(refresh_token)

        # Check if blacklisted
        jti = payload.get("jti")
        if not jti:
            raise WrextAuthenticationException(
                message="Token missing JTI",
                context={"note": "Old token format not supported"}
            )

        if is_token_blacklisted(jti, self.db):
            raise WrextAuthenticationException(
                message="Refresh token has been revoked",
                context={"reason": "Token blacklisted"}
            )

        # Get user
        user_id = payload.get("id")
        db_user = self.db.query(Users).filter(Users.id == user_id).first()

        if not db_user:
            raise WrextAuthenticationException(
                message="User not found",
                context={"user_id": user_id}
            )

        if db_user.status != "active":
            raise WrextAuthenticationException(
                message="User account is not active",
                context={"status": db_user.status}
            )

        # Get current roles and permissions
        role_names = [ur.role.name for ur in db_user.user_roles if ur.is_primary]

        permission_names = (
            self.db.query(Permission.name)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .join(UserRole, UserRole.role_id == RolePermission.role_id)
            .filter(UserRole.user_id == db_user.id)
            .filter(UserRole.workspace_id == None)
            .distinct()
            .all()
        )
        permissions = [p.name for p in permission_names]

        # Create new token pair
        token_data = {
            "id": str(db_user.id),
            "username": db_user.username,
            "email": db_user.email,
            "roles": role_names,
            "permissions": permissions
        }
        new_access_token = create_access_token(data=token_data)
        new_refresh_token = create_refresh_token(data=token_data)

        # Blacklist old refresh token
        blacklist_entry = TokenBlacklist(
            jti=jti,
            token_type="refresh",
            user_id=db_user.id,
            revoked_at=datetime.utcnow(),
            expires_at=datetime.utcfromtimestamp(payload.get("exp")),
            reason="refresh"
        )
        self.db.add(blacklist_entry)
        self.db.flush()

        logger.info(
            f"Token refreshed for user: {user_id}",
            extra={"old_jti": jti}
        )

        return {
            "access_token": new_access_token,
            "refresh_token": new_refresh_token,
            "token_type": "bearer"
        }

    async def logout_user(self, user_id: UUID, jti: str, exp: int) -> None:
        """
        Logout user by blacklisting token and deactivating session.

        Args:
            user_id: User UUID
            jti: Token JTI
            exp: Token expiration timestamp

        Raises:
            WrextAuthenticationException: If token missing JTI
        """
        if not jti:
            raise WrextAuthenticationException(
                message="Token missing JTI",
                context={"note": "Old token format not supported"}
            )

        # Check if already blacklisted
        if is_token_blacklisted(jti, self.db):
            logger.info(f"Token already blacklisted for user {user_id}")
            return

        # Blacklist access token
        blacklist_entry = TokenBlacklist(
            jti=jti,
            token_type="access",
            user_id=user_id,
            revoked_at=datetime.utcnow(),
            expires_at=datetime.utcfromtimestamp(exp),
            reason="logout"
        )
        self.db.add(blacklist_entry)

        # Deactivate session
        session = self.db.query(UserSession).filter(
            UserSession.jti == jti,
            UserSession.is_active == True
        ).first()

        if session:
            session.is_active = False
            session.revoked_at = datetime.utcnow()

        self.db.flush()

        logger.info(
            f"User logged out: {user_id}",
            extra={"jti": jti}
        )

    async def initiate_password_reset(self, email: str) -> Tuple[Users, str]:
        """
        Generate password reset token.

        Args:
            email: User email

        Returns:
            Tuple of (User object, reset_token)

        Raises:
            ResourceNotFoundException: If user not found
        """
        user = self.db.query(Users).filter(Users.email == email).first()

        if not user:
            raise ResourceNotFoundException(
                resource_type="User",
                resource_id=email
            )

        # Generate reset token (valid 1 hour)
        reset_token = create_verification_token({"user_id": str(user.id)})

        logger.info(
            f"Password reset initiated for user: {user.id}",
            extra={"email": email}
        )

        return user, reset_token

    async def complete_password_reset(self, token: str, new_password: str) -> Users:
        """
        Reset password using token.

        Args:
            token: Reset token
            new_password: New plain text password

        Returns:
            User object

        Raises:
            WrextAuthenticationException: If token invalid
            ResourceNotFoundException: If user not found
        """
        payload = verify_token(token)
        user_id = payload.get("user_id")

        if not user_id:
            raise WrextAuthenticationException(
                message="Invalid token payload",
                context={"error": "Missing user_id"}
            )

        user = self.db.query(Users).filter(Users.id == user_id).first()

        if not user:
            raise ResourceNotFoundException(
                resource_type="User",
                resource_id=user_id
            )

        # Hash and update password
        hashed_pwd = hash_password(new_password)
        user.password_hash = hashed_pwd
        self.db.flush()

        logger.info(
            f"Password reset completed for user: {user_id}",
            extra={"email": user.email}
        )

        return user

    # ========================================================================
    # Private Helper Methods
    # ========================================================================

    def _get_or_create_default_role(self) -> Role:
        """
        Get or create default 'user' role.

        Returns:
            Role object
        """
        default_role = self.db.query(Role).filter(Role.name == "user").first()

        if not default_role:
            default_role = Role(
                name="user",
                display_name="User",
                description="Default role for regular users",
                hierarchy_level=1,
                is_system_role=True,
                created_at=datetime.utcnow()
            )
            self.db.add(default_role)
            self.db.flush()
            logger.info("Created default user role")

        return default_role

    def _get_trial_plan(self) -> Optional[SubscriptionPlan]:
        """
        Get trial subscription plan.

        Returns:
            SubscriptionPlan object for trial, or None if not found
        """
        trial_plan = self.db.query(SubscriptionPlan).filter(
            SubscriptionPlan.name == "trial",
            SubscriptionPlan.is_active == True
        ).first()

        if not trial_plan:
            logger.warning("Trial subscription plan not found in database")

        return trial_plan
