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

import asyncio
from typing import Tuple, Dict, Any, Optional
from uuid import UUID
from datetime import datetime, timezone, timedelta
from src.utils.password_utils import validate_password_strength

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from src.api.models.user_models.users import Users
from src.api.models.user_models.roles import Role
from src.api.models.user_models.user_roles import UserRole
from src.api.models.user_models.permissions import Permission
from src.api.models.user_models.role_permissions import RolePermission
from src.api.models.user_models.token_blacklist import TokenBlacklist
from src.api.models.user_models.user_sessions import UserSession
from src.api.models.audit_models.audit_logs import AuditLog
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
    create_reset_token,
    create_verification_token,
    decode_and_verify_token,
    verify_refresh_token,
    is_token_blacklisted,
)
from fastapi import BackgroundTasks
from src.services.notification_helper import schedule_if_allowed
from src.utils.logger import logger
from src.api.middleware.exceptions import (
    DuplicateResourceException,
    RextAuthenticationException,
    ResourceNotFoundException,
)
from src.api.schema.response_schemas import ErrorCode

# Matches the Redis grace-window TTL used in the /refresh route
# (cache.set(f"refresh_grace:{old_jti}", tokens, ttl=60)) — the DB-backed
# fallback in _db_grace_replay uses the same window so behavior is
# consistent whether or not Redis is available during rotation.
REFRESH_ROTATION_GRACE_SECONDS = 60


class AuthService:
    """Service for authentication business logic"""

    # Default permissions assigned to new users during registration
    # Using tuple to prevent accidental mutation
    DEFAULT_PERMISSIONS: tuple[str, ...] = (
        "user.update",
        "user.read",
        "workspace.create",
        "subscription.read",
    )

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
        password: str,
        full_name: str
    ) -> Tuple[Users, str]:
        """
        Register new user with role assignment and trial subscription.

        Business Rules:
        - Email must be unique
        - Password is hashed before storage
        - Default 'user' role is assigned
        - Trial subscription is auto-assigned (14 days)
        - Verification token is generated (valid 24 hours)

        Args:
            email: User email
            password: Plain text password
            full_name: Full name

        Returns:
            Tuple of (User object, verification_token)

        Raises:
            DuplicateResourceException: If email exists
        """
        # Check if user exists
        result = await self.db.execute(
            select(Users).where(Users.email == email)
        )
        existing_user = result.scalar_one_or_none()

        if existing_user:
            raise DuplicateResourceException(
                message="A user with this email already exists",
                resource_type="user",
                conflicting_field="email"
            )
        
        # Validate password strength
        validate_password_strength(password)

        # Hash password
        hashed_pwd = hash_password(password)

        # Create user
        new_user = Users(
            full_name=full_name,
            email=email,
            password_hash=hashed_pwd,
            created_at=datetime.now(timezone.utc)
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
            assigned_at=datetime.now(timezone.utc),
            assigned_by_user_id=new_user.id
        )
        self.db.add(user_role)
        await self.db.flush()

        # also assign default permissions to the role
        await self._assign_default_permissions_to_role(default_role)


        # Create trial subscription (auto-assigned on signup)
        trial_plan = await self._get_trial_plan()
        if trial_plan:
            trial_start = datetime.now(timezone.utc)
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

            if trial_plan.credits_per_month:
                from src.services.usage_tracking_service import UsageTrackingService
                await UsageTrackingService(self.db).allocate_credits(new_user.id, trial_plan.credits_per_month)

            logger.info(
                f"Trial subscription created for user: {new_user.id}",
                extra={"plan_id": str(trial_plan.id), "trial_end": trial_end.isoformat()}
            )

        # Generate verification token
        verification_token = create_verification_token({"user_id": str(new_user.id)})

        logger.info(
            f"User registered: {new_user.id}",
            extra={"email": email, "has_trial": trial_plan is not None}
        )

        return new_user, verification_token

    async def login_user(
        self,
        email: str,
        password: str,
        device_info: Dict[str, str],
        background_tasks: Optional[BackgroundTasks] = None,
        confirm_reactivation: bool = False,
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
            background_tasks: Optional background tasks for notifications

        Returns:
            Tuple of (User object, tokens dict with access_token, refresh_token, token_type)

        Raises:
            RextAuthenticationException: If credentials invalid or account locked
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
            raise RextAuthenticationException(
                message="Invalid email or password",
                context={"login_attempt": email}
            )

        # Check if account is locked
        if db_user.locked_until and db_user.locked_until > datetime.now(timezone.utc):
            raise RextAuthenticationException(
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
                db_user.locked_until = datetime.now(timezone.utc) + timedelta(hours=lockout_hours)

            await self.db.flush()

            audit_log = AuditLog(
                user_id=db_user.id,
                action="auth.login.failed",
                resource_type="user",
                resource_id=str(db_user.id),
                ip_address=device_info.get("ip_address") if device_info else None,
                user_agent=device_info.get("user_agent") if device_info else None,
                status="failed",
                audit_metadata={"reason": "invalid_password", "device_type": device_info.get("device_type") if device_info else None}
            )
            self.db.add(audit_log)
            await self.db.flush()

            raise RextAuthenticationException(
                message="Invalid email or password",
                context={"login_attempt": email}
            )

        from src.api.config import get_settings
        if get_settings().REQUIRE_EMAIL_VERIFICATION and not db_user.email_verified:
            raise RextAuthenticationException(
                message="Please verify your email address before logging in. Check your inbox for the verification link.",
                context={"email": email}
            )

        # Account status handling (after password verification so status
        # information is never leaked on wrong-password attempts)
        if db_user.deleted_at is not None:
            raise RextAuthenticationException(
                message="This account has been deleted and can no longer be used.",
                context={"email": email}
            )

        if db_user.status in ("banned", "suspended"):
            raise RextAuthenticationException(
                message=f"Your account has been {db_user.status}. Please contact support for assistance.",
                context={"status": db_user.status}
            )

        if db_user.status == "inactive":
            # Deactivated account logging back in within the 14-day grace
            # period (deleted_at is still NULL). Don't reactivate silently —
            # the frontend must show a confirmation popup first and retry
            # with confirm_reactivation=True.
            if not confirm_reactivation:
                raise RextAuthenticationException(
                    message="This account has been deactivated. Would you like to reactivate it?",
                    error_code=ErrorCode.ACCOUNT_DEACTIVATED,
                    context={
                        "requires_reactivation": True,
                        "deactivated_at": db_user.deactivated_at.isoformat() if db_user.deactivated_at else None,
                    }
                )

            # Confirmed — reactivate, cancelling the scheduled permanent deletion.
            db_user.status = "active"
            db_user.deactivated_at = None

            self.db.add(AuditLog(
                user_id=db_user.id,
                action="user.reactivate_on_login",
                resource_type="user",
                resource_id=str(db_user.id),
                ip_address=device_info.get("ip_address") if device_info else None,
                user_agent=device_info.get("user_agent") if device_info else None,
                status="success",
                audit_metadata={"reason": "login_within_grace_period"}
            ))

            logger.info(
                f"Deactivated account reactivated on login: {db_user.id}",
                extra={"email": email}
            )

        # Successful login - reset failed attempts
        db_user.failed_login_attempts = 0
        db_user.last_login_at = datetime.now(timezone.utc)
        db_user.login_count = (db_user.login_count or 0) + 1
        await self.db.flush()

        audit_log = AuditLog(
            user_id=db_user.id,
            action="auth.login",
            resource_type="user",
            resource_id=str(db_user.id),
            ip_address=device_info.get("ip_address") if device_info else None,
            user_agent=device_info.get("user_agent") if device_info else None,
            status="success",
            audit_metadata={"device_type": device_info.get("device_type") if device_info else None, "device_name": device_info.get("device_name") if device_info else None}
        )
        self.db.add(audit_log)
        await self.db.flush()

        # Auto-accept pending workspace invitations for this user
        # This ensures existing users see workspaces they were invited to
        await self._auto_accept_pending_invitations(db_user, self.db, background_tasks)

        # Check for trial expiration and send notification
        if background_tasks:
            # Get user subscription
            sub_result = await self.db.execute(
                select(UserSubscription).where(
                    UserSubscription.user_id == db_user.id,
                    UserSubscription.status == SubscriptionStatus.TRIAL
                )
            )
            subscription = sub_result.scalar_one_or_none()
            
            if subscription and subscription.trial_end_date:
                trial_end = subscription.trial_end_date
                if trial_end.tzinfo is None:
                    trial_end = trial_end.replace(tzinfo=timezone.utc)
                    
                if trial_end < datetime.now(timezone.utc):
                    await schedule_if_allowed(
                        db=self.db,
                        user_id=str(db_user.id),
                        background_tasks=background_tasks,
                        pref_flag="billing_trial_ending",
                        message="Your trial period has ended.",
                        payload={
                            "subscription_id": str(subscription.id),
                            "trial_end_date": subscription.trial_end_date.isoformat(),
                            "plan_id": str(subscription.plan_id)
                        },
                        workspace_id=None,
                    )

        # Get GLOBAL roles only (workspace_id is NULL and is_primary is True)
        # These are platform-level roles: super_admin, admin, user
        # Query fresh from DB to include any roles created during auto-accept
        global_roles_result = await self.db.execute(
            select(Role.name)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(UserRole.user_id == db_user.id)
            .where(UserRole.workspace_id.is_(None))
            .where(UserRole.is_primary.is_(True))
        )
        global_role_names = list(global_roles_result.scalars().all())
        
        #  Get the permission based on the roles
        result = await self.db.execute(
            select(Permission.name)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .join(Role, Role.id == RolePermission.role_id)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(UserRole.user_id == db_user.id)
            .where(UserRole.workspace_id.is_(None))  # global roles only
            .where(UserRole.is_primary.is_(True))
            .distinct()
        )
        global_permissions = list(result.scalars().all())

        # Prepare token data with ONLY global/platform permissions
        # Workspace permissions will be loaded separately via /workspaces/{id}/permissions endpoint
        token_data = {
            "id": str(db_user.id),
            "email": db_user.email,
            "roles": global_role_names,
            "permissions": global_permissions  # Only platform-level permissions
        }

        # Generate tokens
        access_token = create_access_token(data=token_data)
        refresh_token = create_refresh_token(data=token_data)

        # Create session
        access_payload = decode_and_verify_token(access_token)
        jti = access_payload.get("jti")
        exp_timestamp = access_payload.get("exp")
        expires_at = datetime.fromtimestamp(exp_timestamp, tz=timezone.utc) if exp_timestamp else datetime.now(timezone.utc) + timedelta(hours=24)

        new_session = UserSession(
            user_id=db_user.id,
            jti=jti,
            device_name=device_info.get("device_name", "Unknown"),
            device_type=device_info.get("device_type", "desktop"),
            user_agent=device_info.get("user_agent", "Unknown"),
            ip_address=device_info.get("ip_address", "Unknown"),
            is_active=True,
            created_at=datetime.now(timezone.utc),
            last_activity_at=datetime.now(timezone.utc),
            expires_at=expires_at
        )
        self.db.add(new_session)
        await self.db.flush()

        logger.info(
            f"User logged in: {db_user.id}",
            extra={"email": email, "session_id": str(new_session.id)}
        )

        from src.api.config import get_settings
        settings = get_settings()
        
        tokens = {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
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
            RextAuthenticationException: If token invalid or user not found
        """
        payload = decode_and_verify_token(token)
        user_id = payload.get("user_id")

        if not user_id:
            raise RextAuthenticationException(
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
            user.email_verified_at = datetime.now(timezone.utc)
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
            RextAuthenticationException: If email already verified
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
            raise RextAuthenticationException(
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

    async def refresh_token(self, refresh_token: str) -> Tuple[Dict[str, str], Optional[str], int]:
        """
        Generate new access token using refresh token.

        Implements token rotation - old refresh token is blacklisted in DB here;
        the caller must write to Redis cache AFTER committing the DB transaction
        to avoid a poisoned cache on rollback.

        Args:
            refresh_token: Refresh token

        Returns:
            Tuple of (tokens dict, old_jti, old_exp) — caller writes Redis after
            commit. old_jti is None when the request was served from the
            grace-window cache (idempotent replay — nothing to commit).

        Raises:
            RextAuthenticationException: If token invalid, blacklisted, or user not active
        """
        # Verify refresh token
        payload = verify_refresh_token(refresh_token)

        # Check if blacklisted
        jti = payload.get("jti")
        if not jti:
            raise RextAuthenticationException(
                message="Token missing JTI",
                context={"note": "Old token format not supported"}
            )

        from src.api.cache.redis_client import cache

        # Idempotent replay: if this token was already rotated within the grace
        # window, return the same new pair. A second tab or duplicate in-flight
        # request survives rotation instead of being logged out with a 401.
        cached_tokens = await cache.get(f"refresh_grace:{jti}")
        if cached_tokens:
            logger.info(
                "Refresh replay within grace window — returning cached token pair",
                extra={"jti": jti}
            )
            return cached_tokens, None, 0

        # Atomically claim this JTI in Redis BEFORE the blacklist check.
        # Rejects concurrent requests with the same token early, before either
        # touches the DB. Falls back to DB IntegrityError if Redis is unavailable.
        claim_key = f"refresh_claim:{jti}"
        claim_acquired = False
        if await cache.ensure_connected():
            try:
                claimed = await cache.redis.set(claim_key, "1", nx=True, ex=30)
                if not claimed:
                    # Another request is already rotating this JTI. Rather than
                    # failing the loser outright (which forced a client-side
                    # logout on every legitimate race — e.g. two tabs, or the
                    # proactive and reactive refresh paths firing together),
                    # briefly poll for the winner's grace-window result and
                    # replay it. Rotation is a single DB write + Redis write,
                    # so it normally lands well within this window.
                    tokens = await self._await_concurrent_refresh(jti)
                    if tokens:
                        return tokens, None, 0
                    raise RextAuthenticationException(
                        message="Refresh token already used",
                        context={"reason": "Concurrent refresh detected — use the new tokens"}
                    )
                claim_acquired = True
            except RextAuthenticationException:
                raise
            except Exception as redis_err:
                logger.warning(
                    "Redis unavailable for refresh claim guard — falling back to DB IntegrityError",
                    extra={"jti": jti, "error": str(redis_err)}
                )

        try:
            return await self._rotate_refresh_tokens(jti, payload)
        except Exception:
            # Release the claim so a legitimate retry isn't locked out for the
            # remaining claim TTL after a transient failure (DB error, etc.).
            if claim_acquired:
                await cache.delete(claim_key)
            raise

    async def _await_concurrent_refresh(
        self,
        jti: str,
        max_wait_seconds: float = 1.5,
        poll_interval_seconds: float = 0.1,
    ) -> Optional[Dict[str, str]]:
        """
        Poll the grace-window cache for a short window while a concurrent
        request holds the refresh claim for this JTI.

        Rotation (DB write + Redis write) normally completes in well under a
        second, so a caller that loses the claim race almost always finds the
        winner's result here instead of being forced into a hard failure.

        Returns:
            The winner's token pair if it becomes available in time, else None.
        """
        from src.api.cache.redis_client import cache

        elapsed = 0.0
        while elapsed < max_wait_seconds:
            await asyncio.sleep(poll_interval_seconds)
            elapsed += poll_interval_seconds
            cached_tokens = await cache.get(f"refresh_grace:{jti}")
            if cached_tokens:
                logger.info(
                    "Concurrent refresh resolved via grace-window poll",
                    extra={"jti": jti, "waited_seconds": round(elapsed, 2)}
                )
                return cached_tokens
        return None

    async def _issue_token_pair_for_user(
        self, db_user: Users
    ) -> Tuple[Dict[str, str], str]:
        """
        Build a fresh access/refresh token pair from a user's current global
        roles/permissions. Shared by normal rotation and by the grace-window
        replay path (_db_grace_replay), which needs an equivalent pair without
        redoing the blacklist/session bookkeeping already done by the winner
        of a concurrent rotation.

        Returns:
            (tokens dict, new_access_token) — callers that need to track the
            new access token's JTI for session updates use the second value.
        """
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
            .where(UserRole.is_primary.is_(True))     # Only primary roles
            .distinct()
        )
        global_permissions = [row[0] for row in result.all()]

        # Create new token pair with ONLY global permissions
        token_data = {
            "id": str(db_user.id),
            "email": db_user.email,
            "roles": global_role_names,
            "permissions": global_permissions
        }
        new_access_token = create_access_token(data=token_data)
        new_refresh_token = create_refresh_token(data=token_data)

        from src.api.config import get_settings
        settings = get_settings()

        tokens = {
            "access_token": new_access_token,
            "refresh_token": new_refresh_token,
            "token_type": "bearer",
            "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
        }
        return tokens, new_access_token

    async def _db_grace_replay(
        self, jti: str, payload: Dict[str, Any]
    ) -> Optional[Dict[str, str]]:
        """
        DB-backed fallback for the Redis grace-window replay in refresh_token().

        When Redis is unavailable or contended during a rotation, two
        concurrent requests carrying the same refresh token (two tabs, or the
        proactive/reactive refresh paths racing) can both reach
        _rotate_refresh_tokens unguarded. The loser gets a non-definitive
        "already used" rejection (caught via the IntegrityError below) and
        the frontend retries — but on retry the JTI is now genuinely
        blacklisted, and without this check that retry would hit the
        definitive "revoked" branch and force a real logout, even though the
        user's session is still valid and was simply rotated by the other
        request.

        Mirrors the Redis grace window using the TokenBlacklist row itself: a
        "refresh" blacklisting less than REFRESH_ROTATION_GRACE_SECONDS old is
        treated as a legitimate concurrent rotation and gets a fresh token
        pair. Anything older, or blacklisted for another reason (logout,
        forced revocation), is a genuine rejection — returns None so the
        caller raises as before.
        """
        result = await self.db.execute(
            select(TokenBlacklist).where(TokenBlacklist.jti == jti)
        )
        entry = result.scalar_one_or_none()
        if not entry or entry.reason != "refresh":
            return None

        age_seconds = (datetime.now(timezone.utc) - entry.revoked_at).total_seconds()
        if age_seconds > REFRESH_ROTATION_GRACE_SECONDS:
            return None

        user_id = payload.get("id")
        result = await self.db.execute(
            select(Users)
            .options(selectinload(Users.user_roles).selectinload(UserRole.role))
            .where(Users.id == user_id)
        )
        db_user = result.scalar_one_or_none()
        if not db_user or db_user.status != "active":
            return None

        tokens, _ = await self._issue_token_pair_for_user(db_user)
        logger.info(
            "Refresh replay via DB grace window (Redis unavailable/contended during rotation)",
            extra={"jti": jti, "age_seconds": round(age_seconds, 2)}
        )
        return tokens

    async def _rotate_refresh_tokens(
        self,
        jti: str,
        payload: Dict[str, Any],
    ) -> Tuple[Dict[str, str], str, int]:
        """
        Rotate a refresh token: blacklist the old JTI in DB, issue a new pair,
        and update the user's session. Called by refresh_token() after the
        Redis claim guard; not intended to be called directly.
        """
        if await is_token_blacklisted(jti, self.db):
            grace_tokens = await self._db_grace_replay(jti, payload)
            if grace_tokens:
                return grace_tokens, None, 0
            raise RextAuthenticationException(
                message="Refresh token has been revoked",
                context={"reason": "Token blacklisted"}
            )

            logger.info(
                "Refresh token race loser reissued fresh tokens (concurrent rotation detected)",
                extra={"jti": jti, "age_seconds": round(age_seconds, 3)},
            )

            # Lost the race to another concurrent request for this exact
            # token (the winner already committed a blacklist row for it
            # moments ago) — the caller held a token that was genuinely
            # valid when they sent it, so hand them a working session
            # instead of forcing a logout. Skip the blacklist insert below;
            # this jti already has one and the unique constraint would reject
            # a duplicate.
            reissue_without_blacklist_insert = True

        # Get user (eagerly load relationships to avoid lazy loading)
        user_id = payload.get("id")
        result = await self.db.execute(
            select(Users)
            .options(selectinload(Users.user_roles).selectinload(UserRole.role))
            .where(Users.id == user_id)
        )
        db_user = result.scalar_one_or_none()

        if not db_user:
            raise RextAuthenticationException(
                message="User not found",
                context={"user_id": user_id}
            )

        if db_user.status != "active":
            raise RextAuthenticationException(
                message="User account is not active",
                context={"status": db_user.status}
            )

        tokens, new_access_token = await self._issue_token_pair_for_user(db_user)

        # Blacklist old refresh token in DB — Redis write happens in the route
        # handler after db.commit() to prevent a poisoned cache on rollback.
        # Skipped when reissuing for a race loser: a blacklist row for this
        # jti already exists (that's how we detected the race above), and
        # inserting a second one would violate the unique constraint on jti.
        old_exp = payload.get("exp", 0)
        if not reissue_without_blacklist_insert:
            blacklist_entry = TokenBlacklist(
                jti=jti,
                token_type="refresh",
                user_id=db_user.id,
                revoked_at=datetime.now(timezone.utc),
                expires_at=datetime.fromtimestamp(old_exp, tz=timezone.utc),
                reason="refresh"
            )
            self.db.add(blacklist_entry)

        # Update session to track new access token JTI and extend expiry.
        new_access_payload = decode_and_verify_token(new_access_token)
        new_jti = new_access_payload.get("jti")
        new_exp_ts = new_access_payload.get("exp")
        new_expires_at = (
            datetime.fromtimestamp(new_exp_ts, tz=timezone.utc)
            if new_exp_ts
            else datetime.now(timezone.utc) + timedelta(hours=24)
        )

        # Sessions store the ACCESS token JTI, not the refresh token JTI.
        # Until a refresh_jti column is added, find the most-recently-active
        # session for this user (ordered by last_activity_at desc).
        existing_session_result = await self.db.execute(
            select(UserSession)
            .where(
                UserSession.user_id == db_user.id,
                UserSession.is_active.is_(True)
            )
            .order_by(UserSession.last_activity_at.desc())
            .limit(1)
        )
        existing_session = existing_session_result.scalar_one_or_none()
        if existing_session:
            existing_session.jti = new_jti
            existing_session.expires_at = new_expires_at
            existing_session.last_activity_at = datetime.now(timezone.utc)
        else:
            new_session = UserSession(
                user_id=db_user.id,
                jti=new_jti,
                device_name="Unknown",
                device_type="desktop",
                user_agent="Unknown",
                ip_address="Unknown",
                is_active=True,
                created_at=datetime.now(timezone.utc),
                last_activity_at=datetime.now(timezone.utc),
                expires_at=new_expires_at,
            )
            self.db.add(new_session)

        try:
            await self.db.flush()
        except IntegrityError as exc:
            # Unique constraint on TokenBlacklist.jti — concurrent refresh used same token
            raise RextAuthenticationException(
                message="Refresh token already used",
                context={"reason": "Concurrent refresh detected — use the new tokens"}
            ) from exc

        logger.info(
            f"Token refreshed for user: {user_id}",
            extra={"old_jti": jti, "new_jti": new_jti}
        )

        return tokens, jti, old_exp

    async def logout_user(
        self,
        user_id: UUID,
        jti: str,
        exp: int,
        refresh_jti: Optional[str] = None,
        refresh_exp: Optional[int] = None,
    ) -> bool:
        """
        Logout user by blacklisting access token (and optionally refresh token).

        Redis writes intentionally omitted — caller must call
        blacklist_token_in_cache() AFTER db.commit().

        Args:
            user_id: User UUID
            jti: Access token JTI
            exp: Access token expiration timestamp
            refresh_jti: Refresh token JTI (optional — blacklists refresh on logout)
            refresh_exp: Refresh token expiration timestamp (required if refresh_jti given)

        Returns:
            True if token was blacklisted, False if already blacklisted (no-op)

        Raises:
            RextAuthenticationException: If token missing JTI
        """
        if not jti:
            raise RextAuthenticationException(
                message="Token missing JTI",
                context={"note": "Old token format not supported"}
            )

        # Check if already blacklisted
        if await is_token_blacklisted(jti, self.db):
            logger.info(f"Token already blacklisted for user {user_id}")
            return False

        now = datetime.now(timezone.utc)

        # Blacklist access token in DB — Redis write done by caller after commit
        self.db.add(TokenBlacklist(
            jti=jti,
            token_type="access",
            user_id=user_id,
            revoked_at=now,
            expires_at=datetime.fromtimestamp(exp, tz=timezone.utc),
            reason="logout"
        ))

        # Also blacklist refresh token if provided
        if refresh_jti and refresh_exp:
            self.db.add(TokenBlacklist(
                jti=refresh_jti,
                token_type="refresh",
                user_id=user_id,
                revoked_at=now,
                expires_at=datetime.fromtimestamp(refresh_exp, tz=timezone.utc),
                reason="logout"
            ))

        # Deactivate session (session stores access JTI, so this lookup is correct)
        result = await self.db.execute(
            select(UserSession).where(
                UserSession.jti == jti,
                UserSession.is_active.is_(True)
            )
        )
        session = result.scalar_one_or_none()

        if session:
            session.is_active = False
            session.revoked_at = now

        await self.db.flush()

        logger.info(
            f"User logged out: {user_id}",
            extra={"jti": jti, "refresh_jti": refresh_jti}
        )
        return True

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

        # Generate reset token (valid 30 minutes)
        reset_token = create_reset_token({"user_id": str(user.id), "email": user.email})

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
            RextAuthenticationException: If token invalid
            ResourceNotFoundException: If user not found
        """
        payload = decode_and_verify_token(token)
        user_id = payload.get("user_id")

        if not user_id:
            raise RextAuthenticationException(
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

        # Validate password strength
        validate_password_strength(new_password)

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
                created_at=datetime.now(timezone.utc)
            )
            self.db.add(default_role)
            await self.db.flush()
            logger.info("Created default user role")

        return default_role

    # also assign default user permissions
    async def _assign_default_permissions_to_role(self, role: Role) -> None:
        """
        Assign default permissions to a role, avoiding duplicates.

        Args:
            role: Role object
        """


        # Get existing permissions for the role to avoid adding duplicates
        existing_perms_result = await self.db.execute(
            select(Permission.name)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .where(RolePermission.role_id == role.id)
        )
        existing_perms = {p_name for p_name, in existing_perms_result}

        permissions_to_add_names = [p for p in self.DEFAULT_PERMISSIONS if p not in existing_perms]

        if not permissions_to_add_names:
            logger.debug(f"Role '{role.name}' already has all default permissions.")
            return

        # Fetch permission objects to add
        permissions_to_add_result = await self.db.execute(
            select(Permission).where(Permission.name.in_(permissions_to_add_names))
        )
        permissions_to_add = permissions_to_add_result.scalars().all()

        for permission in permissions_to_add:
            self.db.add(RolePermission(role_id=role.id, permission_id=permission.id))

        if permissions_to_add:
            await self.db.flush()
            logger.info(f"Assigned {len(permissions_to_add)} missing default permissions to role: {role.name}")

    async def _get_trial_plan(self) -> Optional[SubscriptionPlan]:
        """
        Get trial subscription plan.

        Returns:
            SubscriptionPlan object for trial, or None if not found
        """
        result = await self.db.execute(
            select(SubscriptionPlan).where(
                SubscriptionPlan.name == "trial",
                SubscriptionPlan.is_active.is_(True)
            )
        )
        trial_plan = result.scalar_one_or_none()

        if not trial_plan:
            logger.warning("Trial subscription plan not found in database")

        return trial_plan

    async def _auto_accept_pending_invitations(self, user: Users, db: AsyncSession, background_tasks: Optional[BackgroundTasks] = None) -> None:
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
            # Use a savepoint so that any DB error inside this block rolls back
            # only the invitation changes, not the parent login transaction
            # (last_login_at, failed_login_attempts resets, etc.).
            async with self.db.begin_nested():
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

            accepted_count = 0
            skipped_count = 0

            for invitation in pending_invitations:
                # Use a savepoint per invitation so a DB failure on one invitation
                # doesn't abort the outer transaction for subsequent iterations.
                try:
                    async with db.begin_nested():
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

                        #  send the notification to user
                        await schedule_if_allowed(
                            db=db,
                            user_id=str(invitation.invited_by_user_id),
                            background_tasks=background_tasks,
                            pref_flag="ws_invite_accepted",
                            message=f"{user.email} has accepted an invitation to join a workspace.",
                            payload = {
                                "user_id": str(user.id),
                                "invitation_id": str(invitation.id),
                                "user_existed": True
                            },
                            workspace_id=str(invitation.workspace_id),
                        )
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

                except Exception as e:
                    # Unexpected error - savepoint was rolled back; log but don't fail login
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
            # Catch-all: Don't fail login if invitation processing fails.
            # The begin_nested() savepoint above ensures the parent transaction
            # (login state updates) is preserved even if this block fails.
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