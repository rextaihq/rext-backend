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
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_

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
    ResourceNotFoundException,
    BusinessRuleViolationException
)


class AuthService:
    """Service for authentication business logic"""

    def __init__(self, db: AsyncSession):
        """
        Initialize AuthService.

        Args:
            db: Async database session
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
        result = await self.db.execute(
            select(Users).where(
                or_(Users.email == email, Users.username == username)
            )
        )
        existing_user = result.scalar_one_or_none()

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
        await self.db.flush()

        # Assign default role
        default_role = await self._get_or_create_default_role()

        user_role = UserRole(
            user_id=new_user.id,
            role_id=default_role.id,
            workspace_id=None,
            is_primary=True,
            assigned_at=datetime.utcnow(),
            assigned_by_user_id=new_user.id
        )
        self.db.add(user_role)
        await self.db.flush()

        # Create trial subscription (auto-assigned on signup)
        trial_plan = await self._get_trial_plan()
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
            await self.db.flush()

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
        # Find user (eagerly load relationships to avoid lazy loading in async context)
        from sqlalchemy.orm import selectinload
        result = await self.db.execute(
            select(Users)
            .options(selectinload(Users.user_roles).selectinload(UserRole.role))
            .where(Users.email == email)
        )
        db_user = result.scalar_one_or_none()

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

            # Lock account if too many failures (configurable via settings)
            from src.api.config import get_settings
            settings = get_settings()
            max_attempts = settings.AUTH_MAX_LOGIN_ATTEMPTS
            lockout_hours = settings.AUTH_LOCKOUT_DURATION_HOURS

            if db_user.failed_login_attempts >= max_attempts:
                db_user.locked_until = datetime.utcnow() + timedelta(hours=lockout_hours)

            await self.db.flush()

            raise WrextAuthenticationException(
                message="Invalid email or password",
                context={"login_attempt": email}
            )

        # Successful login - reset failed attempts
        db_user.failed_login_attempts = 0
        db_user.last_login_at = datetime.utcnow()
        db_user.login_count = (db_user.login_count or 0) + 1
        await self.db.flush()

        # Auto-accept pending workspace invitations for this user
        # This ensures existing users see workspaces they were invited to
        await self._auto_accept_pending_invitations(db_user)

        # Get GLOBAL roles only (workspace_id is NULL and is_primary is True)
        # These are platform-level roles: super_admin, admin, user
        # Query fresh from DB to include any roles created during auto-accept
        global_roles_result = await self.db.execute(
            select(Role.name)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(UserRole.user_id == db_user.id)
            .where(UserRole.workspace_id.is_(None))
            .where(UserRole.is_primary == True)
        )
        global_role_names = list(global_roles_result.scalars().all())

        # Get GLOBAL permissions only (from global roles)
        # These are platform-level permissions: user.*, workspace.create, subscription.*, etc.
        # Workspace-specific permissions (topic.*, content.*, etc.) are loaded dynamically per workspace
        result = await self.db.execute(
            select(Permission.name)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .join(UserRole, UserRole.role_id == RolePermission.role_id)
            .where(UserRole.user_id == db_user.id)
            .where(UserRole.workspace_id == None)  # Only global role assignments
            .where(UserRole.is_primary == True)     # Only primary roles
            .distinct()
        )
        global_permissions = [row[0] for row in result.all()]

        # Prepare token data with ONLY global/platform permissions
        # Workspace permissions will be loaded separately via /workspaces/{id}/permissions endpoint
        token_data = {
            "id": str(db_user.id),
            "username": db_user.username,
            "email": db_user.email,
            "roles": global_role_names,
            "permissions": global_permissions  # Only platform-level permissions
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
        await self.db.flush()

        logger.info(
            f"User logged in: {db_user.id}",
            extra={"email": email, "session_id": str(new_session.id)}
        )

        tokens = {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "permissions": global_permissions,  # Include permissions for route response
            "roles": global_role_names  # Include roles for route response
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

        result = await self.db.execute(
            select(Users).where(Users.id == user_id)
        )
        user = result.scalar_one_or_none()

        if not user:
            raise ResourceNotFoundException(
                resource_type="User",
                resource_id=user_id
            )

        if not user.email_verified:
            user.email_verified = True
            user.email_verified_at = datetime.utcnow()
            await self.db.flush()

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
        result = await self.db.execute(
            select(Users).where(Users.email == email)
        )
        user = result.scalar_one_or_none()

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
        await self.db.flush()

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

        if await is_token_blacklisted(jti, self.db):
            raise WrextAuthenticationException(
                message="Refresh token has been revoked",
                context={"reason": "Token blacklisted"}
            )

        # Get user
        user_id = payload.get("id")
        result = await self.db.execute(
            select(Users).where(Users.id == user_id)
        )
        db_user = result.scalar_one_or_none()

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

        # Get GLOBAL roles only (workspace_id is NULL and is_primary is True)
        global_role_names = [
            ur.role.name
            for ur in db_user.user_roles
            if ur.workspace_id is None and ur.is_primary
        ]

        # Get GLOBAL permissions only (from global roles)
        result = await self.db.execute(
            select(Permission.name)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .join(UserRole, UserRole.role_id == RolePermission.role_id)
            .where(UserRole.user_id == db_user.id)
            .where(UserRole.workspace_id == None)  # Only global role assignments
            .where(UserRole.is_primary == True)     # Only primary roles
            .distinct()
        )
        global_permissions = [row[0] for row in result.all()]

        # Create new token pair with ONLY global permissions
        token_data = {
            "id": str(db_user.id),
            "username": db_user.username,
            "email": db_user.email,
            "roles": global_role_names,
            "permissions": global_permissions
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
        await self.db.flush()

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
        if await is_token_blacklisted(jti, self.db):
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
        result = await self.db.execute(
            select(UserSession).where(
                UserSession.jti == jti,
                UserSession.is_active == True
            )
        )
        session = result.scalar_one_or_none()

        if session:
            session.is_active = False
            session.revoked_at = datetime.utcnow()

        await self.db.flush()

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
        result = await self.db.execute(select(Users).where(Users.email == email))
        user = result.scalar_one_or_none()

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

        result = await self.db.execute(
            select(Users).where(Users.id == user_id)
        )
        user = result.scalar_one_or_none()

        if not user:
            raise ResourceNotFoundException(
                resource_type="User",
                resource_id=user_id
            )

        # Hash and update password
        hashed_pwd = hash_password(new_password)
        user.password_hash = hashed_pwd
        await self.db.flush()

        logger.info(
            f"Password reset completed for user: {user_id}",
            extra={"email": user.email}
        )

        return user

    # ========================================================================
    # Private Helper Methods
    # ========================================================================

    async def _get_or_create_default_role(self) -> Role:
        """
        Get or create default 'user' role.

        Returns:
            Role object
        """
        result = await self.db.execute(
            select(Role).where(Role.name == "user")
        )
        default_role = result.scalar_one_or_none()

        if not default_role:
            default_role = Role(
                name="user",
                display_name="User",
                description="Default role for regular users",
                hierarchy_level=1,
                is_system_role=True,
                is_workspace_role=False,  # Platform role, not workspace role
                created_at=datetime.utcnow()
            )
            self.db.add(default_role)
            await self.db.flush()
            logger.info("Created default user role")

        return default_role

    async def _get_trial_plan(self) -> Optional[SubscriptionPlan]:
        """
        Get trial subscription plan.

        Returns:
            SubscriptionPlan object for trial, or None if not found
        """
        result = await self.db.execute(
            select(SubscriptionPlan).where(
                SubscriptionPlan.name == "trial",
                SubscriptionPlan.is_active == True
            )
        )
        trial_plan = result.scalar_one_or_none()

        if not trial_plan:
            logger.warning("Trial subscription plan not found in database")

        return trial_plan

    async def _auto_accept_pending_invitations(self, user: Users) -> None:
        """
        Auto-accept all pending workspace invitations for a user during login.

        This ensures that existing users who were invited to a workspace
        will see that workspace immediately after logging in, without needing
        to manually accept the invitation.

        The method is designed to be fault-tolerant:
        - If invitation acceptance fails, it logs the error but doesn't fail login
        - Skips expired invitations automatically
        - Handles race conditions gracefully

        Args:
            user: User object who just logged in

        Side Effects:
            - Creates WorkspaceMembers records
            - Creates UserRole records
            - Updates UserInvitations.status to "accepted"
        """
        from src.services.invitation_service import InvitationService
        from src.utils.invitation_utils import is_invitation_expired

        logger.info(
            f"[AUTO-ACCEPT] Starting auto-accept process for user during login",
            extra={
                "user_id": str(user.id),
                "user_email": user.email
            }
        )

        try:
            invitation_service = InvitationService(self.db)

            # Get all pending invitations for this user's email
            pending_invitations = await invitation_service.get_invitations_by_email(
                email=user.email,
                status="pending"
            )

            logger.info(
                f"[AUTO-ACCEPT] Query completed - found {len(pending_invitations)} pending invitation(s)",
                extra={
                    "user_id": str(user.id),
                    "user_email": user.email,
                    "invitation_count": len(pending_invitations),
                    "invitation_ids": [str(inv.id) for inv in pending_invitations]
                }
            )

            if not pending_invitations:
                logger.info(
                    f"[AUTO-ACCEPT] No pending invitations found for {user.email} - skipping",
                    extra={"user_id": str(user.id)}
                )
                return  # No pending invitations, nothing to do

            accepted_count = 0
            skipped_count = 0

            for invitation in pending_invitations:
                try:
                    logger.info(
                        f"[AUTO-ACCEPT] Processing invitation {str(invitation.id)}",
                        extra={
                            "invitation_id": str(invitation.id),
                            "workspace_id": str(invitation.workspace_id),
                            "role_id": str(invitation.role_id),
                            "status": invitation.status,
                            "expires_at": invitation.expires_at.isoformat()
                        }
                    )

                    # Skip expired invitations
                    if is_invitation_expired(invitation):
                        invitation.status = "expired"
                        skipped_count += 1
                        logger.warning(
                            f"[AUTO-ACCEPT] Skipping expired invitation",
                            extra={
                                "invitation_id": str(invitation.id),
                                "workspace_id": str(invitation.workspace_id),
                                "expires_at": invitation.expires_at.isoformat()
                            }
                        )
                        continue

                    logger.info(
                        f"[AUTO-ACCEPT] Calling accept_invitation service method",
                        extra={
                            "invitation_id": str(invitation.id),
                            "user_id": str(user.id),
                            "workspace_id": str(invitation.workspace_id)
                        }
                    )

                    # Auto-accept the invitation
                    # This creates WorkspaceMembers + UserRole records
                    result = await invitation_service.accept_invitation(
                        invitation_id=invitation.id,
                        user_id=user.id
                    )

                    accepted_count += 1
                    logger.info(
                        f"[AUTO-ACCEPT] ✅ Successfully auto-accepted invitation during login",
                        extra={
                            "user_id": str(user.id),
                            "invitation_id": str(invitation.id),
                            "workspace_id": str(invitation.workspace_id),
                            "membership_id": result["membership_id"],
                            "result": result
                        }
                    )

                except BusinessRuleViolationException as e:
                    # User might already be a member - this is OK, just skip
                    if "already a member" in str(e):
                        skipped_count += 1
                        logger.info(
                            f"[AUTO-ACCEPT] User already member of workspace (invitation already marked accepted)",
                            extra={
                                "user_id": str(user.id),
                                "invitation_id": str(invitation.id),
                                "workspace_id": str(invitation.workspace_id),
                                "error": str(e)
                            }
                        )
                        # Note: invitation.status already set to "accepted" by accept_invitation before raising
                    else:
                        # Other business rule violations - log and continue
                        logger.error(
                            f"[AUTO-ACCEPT] ❌ Business rule violation - failed to auto-accept invitation: {str(e)}",
                            extra={
                                "user_id": str(user.id),
                                "invitation_id": str(invitation.id),
                                "workspace_id": str(invitation.workspace_id),
                                "error": str(e),
                                "error_type": type(e).__name__
                            }
                        )
                        skipped_count += 1

                except Exception as e:
                    # Unexpected error - log but don't fail login
                    logger.error(
                        f"[AUTO-ACCEPT] ❌ Unexpected error auto-accepting invitation: {str(e)}",
                        exc_info=True,
                        extra={
                            "user_id": str(user.id),
                            "invitation_id": str(invitation.id),
                            "workspace_id": str(invitation.workspace_id),
                            "error": str(e),
                            "error_type": type(e).__name__
                        }
                    )
                    skipped_count += 1

            # Flush changes to database
            logger.info(
                f"[AUTO-ACCEPT] Flushing database changes",
                extra={
                    "user_id": str(user.id),
                    "accepted_count": accepted_count,
                    "skipped_count": skipped_count
                }
            )
            await self.db.flush()

            logger.info(
                f"[AUTO-ACCEPT] ✅ Process completed - auto-accepted {accepted_count} invitation(s), skipped {skipped_count}",
                extra={
                    "user_id": str(user.id),
                    "user_email": user.email,
                    "accepted": accepted_count,
                    "skipped": skipped_count,
                    "total_processed": len(pending_invitations)
                }
            )

        except Exception as e:
            # Catch-all: Don't fail login if invitation processing fails
            logger.error(
                f"[AUTO-ACCEPT] ❌ Fatal error - failed to process pending invitations during login: {str(e)}",
                exc_info=True,
                extra={
                    "user_id": str(user.id),
                    "user_email": user.email,
                    "error": str(e),
                    "error_type": type(e).__name__
                }
            )
