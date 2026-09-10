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

import hashlib
import hmac
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple
from uuid import UUID, uuid4

from fastapi import BackgroundTasks
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.config import get_settings
from src.api.middleware.exceptions import (
    DuplicateResourceException,
    ResourceNotFoundException,
    RextAuthenticationException,
)
from src.api.models.audit_models.audit_logs import AuditLog
from src.api.models.subscription_models.plans import SubscriptionPlan
from src.api.models.subscription_models.subscriptions import (
    BillingPeriod,
    SubscriptionStatus,
    UserSubscription,
)
from src.api.models.user_models.permissions import Permission
from src.api.models.user_models.role_permissions import RolePermission
from src.api.models.user_models.roles import Role
from src.api.models.user_models.token_blacklist import TokenBlacklist
from src.api.models.user_models.user_roles import UserRole
from src.api.models.user_models.user_sessions import UserSession
from src.api.models.user_models.users import Users
from src.api.schema.response_schemas import ErrorCode
from src.api.security.token_utils import (
    create_access_token,
    create_refresh_token,
    create_reset_token,
    create_verification_token,
    decode_and_verify_token,
    hash_password,
    verify_password,
    verify_refresh_token,
)
from src.services.notification_helper import schedule_if_allowed
from src.utils.logger import logger
from src.utils.password_utils import validate_password_strength

_REFRESH_ROTATION_REASON_PREFIX = "refresh:v1:"
_MAX_REFRESH_REPLAY_HOPS = 32


def _refresh_advisory_lock_key(jti: str) -> int:
    """Return a stable signed bigint for PostgreSQL's advisory lock API."""
    digest = hashlib.sha256(f"refresh-lock:v1\0{jti}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], byteorder="big", signed=True)


def _canonical_revoked_at(revoked_at: datetime) -> str:
    """Serialize a Postgres timestamp without platform-dependent formatting."""
    if revoked_at.tzinfo is None:
        revoked_at = revoked_at.replace(tzinfo=timezone.utc)
    revoked_at = revoked_at.astimezone(timezone.utc)
    return revoked_at.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _derive_successor_refresh_jti(old_jti: str, revoked_at: datetime) -> str:
    """Derive the one valid successor JTI for a version-1 rotation row."""
    message = (f"refresh-successor:v1\0{old_jti}\0{_canonical_revoked_at(revoked_at)}").encode(
        "utf-8"
    )
    digest = hmac.new(
        get_settings().REFRESH_SECRET_KEY.encode("utf-8"),
        message,
        hashlib.sha256,
    ).digest()
    return str(UUID(bytes=digest[:16], version=5))


def _rotation_reason(successor_exp: int) -> str:
    return f"{_REFRESH_ROTATION_REASON_PREFIX}{successor_exp}"


def _parse_rotation_reason(reason: Optional[str]) -> Optional[int]:
    """Parse only rows written by the deterministic rotation implementation."""
    if not reason or not reason.startswith(_REFRESH_ROTATION_REASON_PREFIX):
        return None
    value = reason[len(_REFRESH_ROTATION_REASON_PREFIX) :]
    if not value.isdigit():
        return None
    return int(value)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


@dataclass(frozen=True)
class LogoutResult:
    changed: bool
    revoked_access_jti: str
    revoked_access_exp: int
    revoked_refresh_jti: Optional[str] = None
    revoked_refresh_exp: Optional[int] = None


class AuthService:
    """Service for authentication business logic"""

    # Default permissions assigned to new users during registration
    # Using tuple to prevent accidental mutation
    DEFAULT_PERMISSIONS: tuple[str, ...] = (
        "user.update",
        "user.read",
        "workspace.create",
        "subscription.read",
        # Licenses are keyed on user_id with no workspace_id: owned by the
        # person, not a workspace, so they are platform-level.
        "license.read",
        "license.view",
    )

    def __init__(self, db: AsyncSession):
        """
        Initialize AuthService.

        Args:
            db: Async database session
        """
        self.db = db

    async def register_user(
        self, email: str, password: str, full_name: str, device_fingerprint: Optional[str] = None
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
            device_fingerprint: Hash of IP + User-Agent captured at signup, used
                to permanently cap free/trial accounts per device (see
                SubscriptionService.count_non_paid_accounts_for_device)

        Returns:
            Tuple of (User object, verification_token)

        Raises:
            DuplicateResourceException: If email exists
        """
        # Check if user exists
        result = await self.db.execute(select(Users).where(Users.email == email))
        existing_user = result.scalar_one_or_none()

        if existing_user:
            raise DuplicateResourceException(
                message="A user with this email already exists",
                resource_type="user",
                conflicting_field="email",
            )

        # Validate password strength
        validate_password_strength(password)

        # Hash password
        hashed_pwd = hash_password(password)

        # Create user
        # last_login_at is set here, not left NULL until the first password
        # login. A session can be established without login_user() ever running
        # -- a token refresh creates one (see _update_session_after_refresh) --
        # so an account could be actively in use while the database still said
        # it had never logged in. Anything reading last_login_at (admin user
        # lists, security pages, activity metrics) silently skipped those users.
        registered_at = datetime.now(timezone.utc)
        new_user = Users(
            full_name=full_name,
            email=email,
            password_hash=hashed_pwd,
            created_at=registered_at,
            last_login_at=registered_at,
            registration_device_fingerprint=device_fingerprint,
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
            assigned_by_user_id=new_user.id,
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
                updated_at=trial_start,
            )
            self.db.add(trial_subscription)
            await self.db.flush()

            if trial_plan.credits_per_month:
                from src.services.usage_tracking_service import UsageTrackingService

                await UsageTrackingService(self.db).allocate_credits(
                    new_user.id, trial_plan.credits_per_month
                )

            logger.info(
                f"Trial subscription created for user: {new_user.id}",
                extra={"plan_id": str(trial_plan.id), "trial_end": trial_end.isoformat()},
            )

        # Generate verification token
        verification_token = create_verification_token({"user_id": str(new_user.id)})

        logger.info(
            f"User registered: {new_user.id}",
            extra={"email": email, "has_trial": trial_plan is not None},
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
            from src.api.models.user_models.invitations import UserInvitations

            invitation_query = (
                select(UserInvitations)
                .where(
                    func.lower(UserInvitations.email) == email.lower(),
                    UserInvitations.status == "pending",
                    UserInvitations.expires_at > datetime.now(timezone.utc),
                )
                .limit(1)
            )
            invitation_result = await self.db.execute(invitation_query)
            pending_invitation = invitation_result.scalar_one_or_none()

            if pending_invitation:
                raise RextAuthenticationException(
                    message="You haven't created a Rext account yet. Please create an account first to accept the invitation.",
                    context={"login_attempt": email, "has_invitation": True},
                )

            raise RextAuthenticationException(
                message="Invalid email or password", context={"login_attempt": email}
            )

        # Check if account is locked
        if db_user.locked_until and db_user.locked_until > datetime.now(timezone.utc):
            raise RextAuthenticationException(
                message="Account is temporarily locked due to multiple failed login attempts. Please try again later.",
                context={"locked_until": db_user.locked_until.isoformat()},
            )

        # Verify password
        is_match = verify_password(password=password, hashed_password=db_user.password_hash)

        if not is_match:
            # Increment failed attempts
            db_user.failed_login_attempts = (db_user.failed_login_attempts or 0) + 1

            # Lock account if too many failures (configurable via settings)
            settings = get_settings()
            max_attempts = settings.AUTH_MAX_LOGIN_ATTEMPTS
            lockout_hours = settings.AUTH_LOCKOUT_DURATION_HOURS

            if db_user.failed_login_attempts >= max_attempts:
                db_user.locked_until = datetime.now(timezone.utc) + timedelta(hours=lockout_hours)

            await self.db.flush()

            audit_log = AuditLog(
                user_id=db_user.id,
                full_name=db_user.full_name or db_user.display_name,
                user_email=db_user.email,
                action="auth.login.failed",
                resource_type="user",
                resource_id=str(db_user.id),
                ip_address=device_info.get("ip_address") if device_info else None,
                user_agent=device_info.get("user_agent") if device_info else None,
                status="failed",
                audit_metadata={
                    "reason": "invalid_password",
                    "device_type": device_info.get("device_type") if device_info else None,
                },
            )
            self.db.add(audit_log)
            await self.db.flush()

            raise RextAuthenticationException(
                message="Invalid email or password", context={"login_attempt": email}
            )

        # if get_settings().REQUIRE_EMAIL_VERIFICATION and not db_user.email_verified:
        #     raise RextAuthenticationException(
        #         message="Please verify your email address before logging in. Check your inbox for the verification link.",
        #         context={"email": email}
        #     )

        # Account status handling (after password verification so status
        # information is never leaked on wrong-password attempts)
        if db_user.deleted_at is not None:
            raise RextAuthenticationException(
                message="This account is scheduled for permanent deletion and can no longer be used. To restore your account, please use the recovery link sent to your email or request a new one via the recovery endpoint.",
                context={"email": email},
            )

        if db_user.status == "suspended":
            # Suspension is temporary and reversible by an admin.
            raise RextAuthenticationException(
                message="Your account has been suspended. Contact support to have it reviewed.",
                error_code=ErrorCode.ACCOUNT_SUSPENDED,
                context={"status": db_user.status},
            )

        if db_user.status == "banned":
            # A ban is permanent — don't imply the user can get back in.
            raise RextAuthenticationException(
                message="Your account has been permanently banned and cannot be used.",
                error_code=ErrorCode.ACCOUNT_BANNED,
                context={"status": db_user.status},
            )

        if db_user.status == "inactive":
            # Deactivated account logging back in within the 14-day grace
            # period (deleted_at is still NULL). Reactivation is never granted
            # by the login call itself — a correct password alone is not proof
            # the mailbox owner wants the account back, so the user must
            # confirm through the emailed recovery link
            # (POST /account-recovery/request -> /account-recovery/verify).
            # confirm_reactivation no longer reactivates anything; it is kept
            # in the request schema only so older clients don't 422.
            raise RextAuthenticationException(
                message="This account has been deactivated. Confirm the emailed link to reactivate it.",
                error_code=ErrorCode.ACCOUNT_DEACTIVATED,
                context={
                    "requires_reactivation": True,
                    "requires_email_verification": True,
                    "deactivated_at": db_user.deactivated_at.isoformat()
                    if db_user.deactivated_at
                    else None,
                },
            )

        # Successful login - reset failed attempts
        db_user.failed_login_attempts = 0
        db_user.last_login_at = datetime.now(timezone.utc)
        db_user.login_count = (db_user.login_count or 0) + 1
        await self.db.flush()

        audit_log = AuditLog(
            user_id=db_user.id,
            full_name=db_user.full_name or db_user.display_name,
            user_email=db_user.email,
            action="auth.login",
            resource_type="user",
            resource_id=str(db_user.id),
            ip_address=device_info.get("ip_address") if device_info else None,
            user_agent=device_info.get("user_agent") if device_info else None,
            status="success",
            new_values={
                "email": db_user.email,
                "full_name": db_user.full_name or db_user.display_name,
                "device_name": device_info.get("device_name") if device_info else None,
                "device_type": device_info.get("device_type") if device_info else None,
                "ip_address": device_info.get("ip_address") if device_info else None,
            },
            audit_metadata={
                "device_type": device_info.get("device_type") if device_info else None,
                "device_name": device_info.get("device_name") if device_info else None,
            },
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
                    UserSubscription.status == SubscriptionStatus.TRIAL,
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
                            "plan_id": str(subscription.plan_id),
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

        # Prepare token data with ONLY global/platform permissions. The stable
        # session ID lets refreshes update the originating session instead of
        # guessing the user's most-recent session.
        session_id = uuid4()
        # Workspace permissions will be loaded separately via /workspaces/{id}/permissions endpoint
        token_data = {
            "id": str(db_user.id),
            "email": db_user.email,
            "roles": global_role_names,
            "permissions": global_permissions,  # Only platform-level permissions
            "session_id": str(session_id),
            "session_kind": "user",
        }

        # Generate tokens
        access_token = create_access_token(data=token_data)
        refresh_token = create_refresh_token(data=token_data)

        # Create session
        access_payload = decode_and_verify_token(access_token)
        refresh_payload = verify_refresh_token(refresh_token)
        jti = access_payload.get("jti")
        exp_timestamp = access_payload.get("exp")
        refresh_exp_timestamp = refresh_payload.get("exp")
        session_expires_at = (
            datetime.fromtimestamp(refresh_exp_timestamp, tz=timezone.utc)
            if refresh_exp_timestamp
            else datetime.now(timezone.utc)
            + timedelta(days=get_settings().REFRESH_TOKEN_EXPIRE_DAYS)
        )

        new_session = UserSession(
            id=session_id,
            user_id=db_user.id,
            jti=jti,
            device_name=device_info.get("device_name", "Unknown"),
            device_type=device_info.get("device_type", "desktop"),
            user_agent=device_info.get("user_agent", "Unknown"),
            ip_address=device_info.get("ip_address", "Unknown"),
            is_active=True,
            created_at=datetime.now(timezone.utc),
            last_activity_at=datetime.now(timezone.utc),
            expires_at=session_expires_at,
            session_metadata={"access_expires_at": int(exp_timestamp)},
        )
        self.db.add(new_session)
        await self.db.flush()

        logger.info(
            f"User logged in: {db_user.id}",
            extra={"email": email, "session_id": str(new_session.id)},
        )
        settings = get_settings()

        tokens = {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            "permissions": global_permissions,  # Include permissions for route response
            "roles": global_role_names,  # Include roles for route response
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
                message="Invalid token payload", context={"error": "Missing user_id"}
            )

        result = await self.db.execute(select(Users).where(Users.id == user_id))
        user = result.scalar_one_or_none()

        if not user:
            raise ResourceNotFoundException(resource_type="User", resource_id=user_id)

        if not user.email_verified:
            user.email_verified = True
            user.email_verified_at = datetime.now(timezone.utc)
            await self.db.flush()

        logger.info(f"Email verified for user: {user_id}", extra={"email": user.email})

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
        result = await self.db.execute(select(Users).where(Users.email == email))
        user = result.scalar_one_or_none()

        if not user:
            raise ResourceNotFoundException(resource_type="User", resource_id=email)

        # Check if already verified
        if user.email_verified:
            raise RextAuthenticationException(
                message="Email is already verified", context={"email": email}
            )

        # Generate new verification token
        verification_token = create_verification_token(data={"user_id": str(user.id)})

        # Update user's verification token
        user.verification_token = verification_token
        await self.db.flush()

        logger.info(f"Verification email resent for user: {user.id}", extra={"email": email})

        return user, verification_token

    async def refresh_token(self, refresh_token: str) -> Tuple[Dict[str, Any], str, int]:
        """Rotate or replay a refresh token with PostgreSQL as authority.

        Every JTI is serialized by a transaction-scoped advisory lock. A
        versioned blacklist row contains enough information to recreate the
        exact successor refresh token after a concurrent request, Redis loss,
        or process restart. Access tokens are intentionally minted afresh from
        the user's current roles and permissions.
        """
        payload = verify_refresh_token(refresh_token)
        original_jti = payload.get("jti")
        user_id = payload.get("id")
        old_exp = int(payload.get("exp") or 0)
        if not original_jti:
            raise RextAuthenticationException(
                message="Token missing JTI",
                context={"note": "Old token format not supported"},
            )
        if not user_id or old_exp <= 0:
            raise RextAuthenticationException(message="Invalid refresh token payload")
        if payload.get("session_kind") == "impersonation" or (
            payload.get("session_id")
            and not payload.get("session_kind")
            and not any(claim in payload for claim in ("email", "roles", "permissions"))
        ):
            raise RextAuthenticationException(
                message="Impersonation refresh tokens are not supported"
            )
        try:
            user_uuid = UUID(str(user_id))
        except (TypeError, ValueError) as exc:
            raise RextAuthenticationException(message="Invalid refresh token subject") from exc

        refresh_claims = {"id": str(user_uuid)}
        if payload.get("session_id"):
            refresh_claims["session_id"] = str(payload["session_id"])
        if payload.get("session_kind") == "user":
            refresh_claims["session_kind"] = "user"

        settings = get_settings()
        current_jti = str(original_jti)
        current_exp = old_exp
        current_refresh_token = refresh_token
        visited: set[str] = set()
        replaying = False

        for _ in range(_MAX_REFRESH_REPLAY_HOPS):
            if current_jti in visited:
                raise RextAuthenticationException(message="Refresh token rotation chain is invalid")
            visited.add(current_jti)

            # Transaction-scoped locks are compatible with PgBouncer's
            # transaction pooling. The stable signed bigint is identical in
            # every worker and Python process.
            await self._acquire_refresh_lock(current_jti)
            blacklist_entry = await self._get_blacklist_entry(current_jti)
            db_now = await self._database_clock()

            if blacklist_entry is None:
                if replaying:
                    # This is the first unconsumed token in the deterministic
                    # lineage. Return it without rotating it again.
                    break

                successor_exp = int(db_now.timestamp()) + (
                    settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60
                )
                successor_jti = _derive_successor_refresh_jti(current_jti, db_now)
                blacklist_entry = TokenBlacklist(
                    jti=current_jti,
                    token_type="refresh",
                    user_id=user_uuid,
                    revoked_at=db_now,
                    expires_at=datetime.fromtimestamp(current_exp, tz=timezone.utc),
                    reason=_rotation_reason(successor_exp),
                )
                self.db.add(blacklist_entry)
                await self.db.flush()

                current_jti = successor_jti
                current_exp = successor_exp
                current_refresh_token = create_refresh_token(
                    refresh_claims,
                    jti=current_jti,
                    expires_at=datetime.fromtimestamp(current_exp, tz=timezone.utc),
                )
                break

            successor_exp = self._validate_replay_entry(
                blacklist_entry=blacklist_entry,
                expected_user_id=user_uuid,
                expected_exp=current_exp,
                db_now=db_now,
            )
            current_jti = _derive_successor_refresh_jti(current_jti, blacklist_entry.revoked_at)
            current_exp = successor_exp
            current_refresh_token = create_refresh_token(
                refresh_claims,
                jti=current_jti,
                expires_at=datetime.fromtimestamp(current_exp, tz=timezone.utc),
            )
            replaying = True
        else:
            raise RextAuthenticationException(message="Refresh token rotation chain is too long")

        (
            db_user,
            global_role_names,
            global_permissions,
        ) = await self._load_current_refresh_authorization(user_uuid)
        access_claims = {
            "id": str(db_user.id),
            "email": db_user.email,
            "roles": global_role_names,
            "permissions": global_permissions,
        }
        if refresh_claims.get("session_id"):
            access_claims["session_id"] = refresh_claims["session_id"]
        if refresh_claims.get("session_kind") == "user":
            access_claims["session_kind"] = "user"

        new_access_token = create_access_token(data=access_claims)
        await self._update_session_after_refresh(
            db_user=db_user,
            access_token=new_access_token,
            session_id=refresh_claims.get("session_id"),
            strict_user_session=refresh_claims.get("session_kind") == "user",
            refresh_exp=current_exp,
        )
        await self.db.flush()

        access_jti = decode_and_verify_token(new_access_token).get("jti")
        logger.info(
            "Refresh token resolved",
            extra={
                "user_id": str(db_user.id),
                "old_jti": original_jti,
                "refresh_jti": current_jti,
                "access_jti": access_jti,
                "replayed": replaying,
            },
        )

        tokens = {
            "access_token": new_access_token,
            "refresh_token": current_refresh_token,
            "token_type": "bearer",
            "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            "roles": global_role_names,
            "permissions": global_permissions,
        }
        return tokens, str(original_jti), old_exp

    async def _acquire_refresh_lock(self, jti: str) -> None:
        await self.db.execute(select(func.pg_advisory_xact_lock(_refresh_advisory_lock_key(jti))))

    async def _get_blacklist_entry(self, jti: str) -> Optional[TokenBlacklist]:
        result = await self.db.execute(select(TokenBlacklist).where(TokenBlacklist.jti == jti))
        return result.scalar_one_or_none()

    async def _blacklist_access_token_if_absent(
        self,
        *,
        jti: str,
        user_id: UUID,
        revoked_at: datetime,
        expires_at: int,
    ) -> bool:
        """Idempotently revoke an access JTI under concurrent logout calls."""
        statement = (
            pg_insert(TokenBlacklist)
            .values(
                jti=jti,
                token_type="access",
                user_id=user_id,
                revoked_at=revoked_at,
                expires_at=datetime.fromtimestamp(expires_at, tz=timezone.utc),
                reason="logout",
            )
            .on_conflict_do_nothing(index_elements=[TokenBlacklist.jti])
            .returning(TokenBlacklist.jti)
        )
        result = await self.db.execute(statement)
        return result.scalar_one_or_none() is not None

    async def _database_clock(self) -> datetime:
        result = await self.db.execute(select(func.clock_timestamp()))
        return _as_utc(result.scalar_one())

    def _validate_replay_entry(
        self,
        *,
        blacklist_entry: TokenBlacklist,
        expected_user_id: Any,
        expected_exp: int,
        db_now: datetime,
    ) -> int:
        """Validate and return a deterministic successor's persisted expiry."""
        successor_exp = _parse_rotation_reason(blacklist_entry.reason)
        if (
            blacklist_entry.token_type != "refresh"
            or successor_exp is None
            or str(blacklist_entry.user_id) != str(expected_user_id)
        ):
            # In particular, legacy reason="refresh" rows used random
            # successors and must never be reconstructed as a new lineage.
            raise RextAuthenticationException(
                message="Refresh token has been revoked",
                context={"reason": "Token blacklisted"},
            )

        stored_exp = int(_as_utc(blacklist_entry.expires_at).timestamp())
        if stored_exp != int(expected_exp):
            raise RextAuthenticationException(
                message="Refresh token rotation record does not match token"
            )

        revoked_at = _as_utc(blacklist_entry.revoked_at)
        age_seconds = (db_now - revoked_at).total_seconds()
        grace_seconds = get_settings().REFRESH_REPLAY_GRACE_SECONDS
        if age_seconds < 0 or age_seconds > grace_seconds:
            raise RextAuthenticationException(
                message="Refresh token has been revoked",
                context={"reason": "Replay grace window expired"},
            )
        if successor_exp <= int(revoked_at.timestamp()):
            raise RextAuthenticationException(message="Refresh token rotation record is invalid")
        return successor_exp

    async def _load_current_refresh_authorization(
        self, user_id: Any
    ) -> Tuple[Users, list[str], list[str]]:
        from sqlalchemy.orm import selectinload

        result = await self.db.execute(
            select(Users)
            .options(selectinload(Users.user_roles).selectinload(UserRole.role))
            .where(Users.id == user_id)
        )
        db_user = result.scalar_one_or_none()
        if not db_user:
            raise RextAuthenticationException(
                message="User not found", context={"user_id": str(user_id)}
            )
        if db_user.status != "active":
            raise RextAuthenticationException(
                message="User account is not active",
                context={"status": db_user.status},
            )

        global_role_names = sorted(
            {
                user_role.role.name
                for user_role in db_user.user_roles
                if user_role.workspace_id is None and user_role.is_primary
            }
        )
        result = await self.db.execute(
            select(Permission.name)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .join(UserRole, UserRole.role_id == RolePermission.role_id)
            .where(UserRole.user_id == db_user.id)
            .where(UserRole.workspace_id.is_(None))
            .where(UserRole.is_primary.is_(True))
            .distinct()
        )
        global_permissions = sorted(result.scalars().all())
        return db_user, global_role_names, global_permissions

    async def _update_session_after_refresh(
        self,
        *,
        db_user: Users,
        access_token: str,
        session_id: Optional[str],
        strict_user_session: bool,
        refresh_exp: int,
    ) -> None:
        access_payload = decode_and_verify_token(access_token)
        access_jti = access_payload.get("jti")
        access_exp = int(access_payload.get("exp") or 0)
        session_expires_at = datetime.fromtimestamp(refresh_exp, tz=timezone.utc)

        existing_session = None
        parsed_session_id = None
        if session_id:
            try:
                parsed_session_id = UUID(str(session_id))
            except (TypeError, ValueError):
                pass

        if strict_user_session:
            if parsed_session_id is None:
                raise RextAuthenticationException(message="Refresh token session is invalid")
            result = await self.db.execute(
                select(UserSession)
                .where(
                    UserSession.id == parsed_session_id,
                    UserSession.user_id == db_user.id,
                )
                .with_for_update()
            )
            existing_session = result.scalar_one_or_none()
            if existing_session is None or not existing_session.is_active:
                raise RextAuthenticationException(message="Refresh token session has been revoked")
        elif parsed_session_id:
            result = await self.db.execute(
                select(UserSession)
                .where(
                    UserSession.id == parsed_session_id,
                    UserSession.user_id == db_user.id,
                    UserSession.is_active.is_(True),
                )
                .with_for_update()
            )
            existing_session = result.scalar_one_or_none()

        # Tokens issued before user-session claims were added (plus OAuth and
        # impersonation refresh tokens) retain the historical fallback.
        if existing_session is None and not strict_user_session:
            result = await self.db.execute(
                select(UserSession)
                .where(
                    UserSession.user_id == db_user.id,
                    UserSession.is_active.is_(True),
                )
                .order_by(UserSession.last_activity_at.desc())
                .limit(1)
                .with_for_update()
            )
            existing_session = result.scalar_one_or_none()

        now = datetime.now(timezone.utc)
        if existing_session:
            existing_session.jti = access_jti
            existing_session.expires_at = session_expires_at
            session_metadata = dict(existing_session.session_metadata or {})
            session_metadata["access_expires_at"] = access_exp
            existing_session.session_metadata = session_metadata
            existing_session.last_activity_at = now
            return

        self.db.add(
            UserSession(
                user_id=db_user.id,
                jti=access_jti,
                device_name="Unknown",
                device_type="desktop",
                user_agent="Unknown",
                ip_address="Unknown",
                is_active=True,
                created_at=now,
                last_activity_at=now,
                expires_at=session_expires_at,
                session_metadata={"access_expires_at": access_exp},
            )
        )

    async def logout_user(
        self,
        user_id: UUID,
        jti: str,
        exp: int,
        refresh_jti: Optional[str] = None,
        refresh_exp: Optional[int] = None,
        session_id: Optional[str] = None,
        strict_user_session: bool = False,
    ) -> LogoutResult:
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
            The actual access and refresh lineage tips revoked by this logout.

        Raises:
            RextAuthenticationException: If token missing JTI
        """
        if not jti:
            raise RextAuthenticationException(
                message="Token missing JTI", context={"note": "Old token format not supported"}
            )
        try:
            user_uuid = UUID(str(user_id))
        except (TypeError, ValueError) as exc:
            raise RextAuthenticationException(message="Invalid user identifier") from exc

        changed = False
        now = await self._database_clock()

        # Redis is deliberately not consulted here. A positive cache entry is
        # only an accelerator; Postgres is the revocation authority.
        if await self._blacklist_access_token_if_absent(
            jti=str(jti),
            user_id=user_uuid,
            revoked_at=now,
            expires_at=int(exp),
        ):
            changed = True

        # Serialize with refresh rotation. If rotation won the race, follow its
        # deterministic lineage and revoke the current tip instead of leaving
        # a newly-issued refresh token usable after logout.
        revoked_refresh_jti = None
        revoked_refresh_exp = None
        if refresh_jti and refresh_exp:
            (
                revoked_refresh_jti,
                revoked_refresh_exp,
                refresh_changed,
            ) = await self._blacklist_refresh_lineage_tip(
                user_id=user_uuid,
                refresh_jti=refresh_jti,
                refresh_exp=int(refresh_exp),
            )
            changed = changed or refresh_changed

        # Refresh may have won the race and replaced the session's access JTI
        # while logout waited for the lineage lock. New-style tokens identify
        # the exact session, allowing logout to revoke that current access JTI.
        session = None
        if strict_user_session and session_id:
            try:
                parsed_session_id = UUID(str(session_id))
            except (TypeError, ValueError):
                parsed_session_id = None
            if parsed_session_id:
                result = await self.db.execute(
                    select(UserSession)
                    .where(
                        UserSession.id == parsed_session_id,
                        UserSession.user_id == user_uuid,
                    )
                    .with_for_update()
                )
                session = result.scalar_one_or_none()
        if session is None:
            result = await self.db.execute(
                select(UserSession).where(UserSession.jti == jti).with_for_update()
            )
            session = result.scalar_one_or_none()

        revoked_access_jti = str(jti)
        revoked_access_exp = int(exp)
        if session:
            revoked_access_jti = str(session.jti or jti)
            metadata_access_exp = (getattr(session, "session_metadata", None) or {}).get(
                "access_expires_at"
            )
            if metadata_access_exp:
                revoked_access_exp = int(metadata_access_exp)
            elif session.expires_at:
                revoked_access_exp = int(_as_utc(session.expires_at).timestamp())
            if revoked_access_jti != str(jti) and await self._blacklist_access_token_if_absent(
                jti=revoked_access_jti,
                user_id=user_uuid,
                revoked_at=await self._database_clock(),
                expires_at=revoked_access_exp,
            ):
                changed = True
            if session.is_active:
                session.is_active = False
                session.revoked_at = await self._database_clock()
                changed = True

        await self.db.flush()

        logger.info(
            f"User logged out: {user_id}",
            extra={
                "jti": jti,
                "refresh_jti": refresh_jti,
                "revoked_refresh_jti": revoked_refresh_jti,
            },
        )
        return LogoutResult(
            changed=changed,
            revoked_access_jti=revoked_access_jti,
            revoked_access_exp=revoked_access_exp,
            revoked_refresh_jti=revoked_refresh_jti,
            revoked_refresh_exp=revoked_refresh_exp,
        )

    async def _blacklist_refresh_lineage_tip(
        self,
        *,
        user_id: Any,
        refresh_jti: str,
        refresh_exp: int,
    ) -> Tuple[Optional[str], Optional[int], bool]:
        """Revoke the current deterministic successor while holding its lock."""
        current_jti = str(refresh_jti)
        current_exp = int(refresh_exp)
        visited: set[str] = set()

        for _ in range(_MAX_REFRESH_REPLAY_HOPS):
            if current_jti in visited:
                raise RextAuthenticationException(message="Refresh token rotation chain is invalid")
            visited.add(current_jti)
            await self._acquire_refresh_lock(current_jti)
            entry = await self._get_blacklist_entry(current_jti)
            db_now = await self._database_clock()

            if entry is None:
                self.db.add(
                    TokenBlacklist(
                        jti=current_jti,
                        token_type="refresh",
                        user_id=user_id,
                        revoked_at=db_now,
                        expires_at=datetime.fromtimestamp(current_exp, tz=timezone.utc),
                        reason="logout",
                    )
                )
                return current_jti, current_exp, True

            successor_exp = _parse_rotation_reason(entry.reason)
            entry_matches = (
                entry.token_type == "refresh"
                and str(entry.user_id) == str(user_id)
                and int(_as_utc(entry.expires_at).timestamp()) == current_exp
            )
            if entry_matches and entry.reason == "logout":
                return current_jti, current_exp, False
            if not entry_matches or successor_exp is None:
                # Already revoked for logout/another cause, or a legacy random
                # lineage that cannot be reconstructed safely.
                return None, None, False

            current_jti = _derive_successor_refresh_jti(current_jti, entry.revoked_at)
            current_exp = successor_exp

        raise RextAuthenticationException(message="Refresh token rotation chain is too long")

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
            raise ResourceNotFoundException(resource_type="User", resource_id=email)

        # Generate reset token (valid 30 minutes)
        reset_token = create_reset_token({"user_id": str(user.id), "email": user.email})

        logger.info(f"Password reset initiated for user: {user.id}", extra={"email": email})

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
                message="Invalid token payload", context={"error": "Missing user_id"}
            )

        result = await self.db.execute(select(Users).where(Users.id == user_id))
        user = result.scalar_one_or_none()

        if not user:
            raise ResourceNotFoundException(resource_type="User", resource_id=user_id)

        # Validate password strength
        validate_password_strength(new_password)

        # Hash and update password
        hashed_pwd = hash_password(new_password)
        user.password_hash = hashed_pwd
        await self.db.flush()

        logger.info(f"Password reset completed for user: {user_id}", extra={"email": user.email})

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
        result = await self.db.execute(select(Role).where(Role.name == "user"))
        default_role = result.scalar_one_or_none()

        if not default_role:
            default_role = Role(
                name="user",
                display_name="User",
                description="Default role for regular users",
                hierarchy_level=1,
                is_system_role=True,
                is_workspace_role=False,  # Platform role, not workspace role
                created_at=datetime.now(timezone.utc),
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
        existing_perms = {p_name for (p_name,) in existing_perms_result}

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
            logger.info(
                f"Assigned {len(permissions_to_add)} missing default permissions to role: {role.name}"
            )

    async def _get_trial_plan(self) -> Optional[SubscriptionPlan]:
        """
        Get trial subscription plan.

        Returns:
            SubscriptionPlan object for trial, or None if not found
        """
        result = await self.db.execute(
            select(SubscriptionPlan).where(
                SubscriptionPlan.name == "trial", SubscriptionPlan.is_active.is_(True)
            )
        )
        trial_plan = result.scalar_one_or_none()

        if not trial_plan:
            logger.warning("Trial subscription plan not found in database")

        return trial_plan

    async def _auto_accept_pending_invitations(
        self, user: Users, db: AsyncSession, background_tasks: Optional[BackgroundTasks] = None
    ) -> None:
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
            "[AUTO-ACCEPT] Starting auto-accept process for user during login",
            extra={"user_id": str(user.id), "user_email": user.email},
        )

        try:
            # Use a savepoint so that any DB error inside this block rolls back
            # only the invitation changes, not the parent login transaction
            # (last_login_at, failed_login_attempts resets, etc.).
            async with self.db.begin_nested():
                invitation_service = InvitationService(self.db)

                # Get all pending invitations for this user's email
                pending_invitations = await invitation_service.get_invitations_by_email(
                    email=user.email, status="pending"
                )

                logger.info(
                    f"[AUTO-ACCEPT] Query completed - found {len(pending_invitations)} pending invitation(s)",
                    extra={
                        "user_id": str(user.id),
                        "user_email": user.email,
                        "invitation_count": len(pending_invitations),
                        "invitation_ids": [str(inv.id) for inv in pending_invitations],
                    },
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
                                "expires_at": invitation.expires_at.isoformat(),
                            },
                        )

                        # Skip expired invitations
                        if is_invitation_expired(invitation):
                            invitation.status = "expired"
                            skipped_count += 1
                            logger.warning(
                                "[AUTO-ACCEPT] Skipping expired invitation",
                                extra={
                                    "invitation_id": str(invitation.id),
                                    "workspace_id": str(invitation.workspace_id),
                                    "expires_at": invitation.expires_at.isoformat(),
                                },
                            )
                            continue

                        #  send the notification to user
                        await schedule_if_allowed(
                            db=db,
                            user_id=str(invitation.invited_by_user_id),
                            background_tasks=background_tasks,
                            pref_flag="ws_invite_accepted",
                            message=f"{user.email} has accepted an invitation to join a workspace.",
                            payload={
                                "user_id": str(user.id),
                                "invitation_id": str(invitation.id),
                                "user_existed": True,
                            },
                            workspace_id=str(invitation.workspace_id),
                        )
                        logger.info(
                            "[AUTO-ACCEPT] Calling accept_invitation service method",
                            extra={
                                "invitation_id": str(invitation.id),
                                "user_id": str(user.id),
                                "workspace_id": str(invitation.workspace_id),
                            },
                        )

                        # Auto-accept the invitation
                        # This creates WorkspaceMembers + UserRole records
                        result = await invitation_service.accept_invitation(
                            invitation_id=invitation.id, user_id=user.id
                        )

                        accepted_count += 1
                        logger.info(
                            "[AUTO-ACCEPT] ✅ Successfully auto-accepted invitation during login",
                            extra={
                                "user_id": str(user.id),
                                "invitation_id": str(invitation.id),
                                "workspace_id": str(invitation.workspace_id),
                                "membership_id": result["membership_id"],
                                "result": result,
                            },
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
                            "error_type": type(e).__name__,
                        },
                    )
                    skipped_count += 1

            logger.info(
                f"[AUTO-ACCEPT] ✅ Process completed - auto-accepted {accepted_count} invitation(s), skipped {skipped_count}",
                extra={
                    "user_id": str(user.id),
                    "user_email": user.email,
                    "accepted": accepted_count,
                    "skipped": skipped_count,
                    "total_processed": len(pending_invitations),
                },
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
                    "error_type": type(e).__name__,
                },
            )
