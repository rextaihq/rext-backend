"""
OAuth Service - Business Logic for OAuth Authentication

This service handles OAuth provider account linking, registration, and login.

Responsibilities:
- OAuth account registration and linking
- OAuth login with automatic user creation
- OAuth account management (link/unlink)
- Provider token storage and refresh

Does NOT:
- Handle HTTP requests/responses (that's routes)
- Commit transactions (that's decorators/routes)
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.api.config import get_settings
from src.api.middleware.exceptions import (
    DuplicateResourceException,
    ResourceNotFoundException,
    RextAuthenticationException,
)
from src.api.models.subscription_models.plans import SubscriptionPlan
from src.api.models.subscription_models.subscriptions import (
    BillingPeriod,
    SubscriptionStatus,
    UserSubscription,
)
from src.api.models.user_models.oauth_accounts import OAuthAccount
from src.api.models.user_models.permissions import Permission
from src.api.models.user_models.role_permissions import RolePermission
from src.api.models.user_models.user_roles import UserRole
from src.api.models.user_models.user_sessions import UserSession
from src.api.models.user_models.users import Users
from src.api.security.token_utils import (
    create_access_token,
    create_refresh_token,
    decode_and_verify_token,
    verify_refresh_token,
)
from src.config.plan_rules import TRIAL_DURATION_DAYS
from src.utils.email_domain_validator import is_disposable_email
from src.utils.logger import logger


class OAuthService:
    """Service for OAuth authentication business logic"""

    def __init__(self, db: AsyncSession):
        """
        Initialize OAuthService.

        Args:
            db: Async database session
        """
        self.db = db

    async def oauth_login_or_register(
        self,
        provider: str,
        provider_account_id: str,
        provider_email: str,
        provider_name: str,
        provider_avatar_url: Optional[str] = None,
        provider_username: Optional[str] = None,
        access_token: Optional[str] = None,
        refresh_token: Optional[str] = None,
        token_expires_at: Optional[datetime] = None,
        email_verified: bool = True,
    ) -> Tuple[Users, Dict[str, Any]]:
        """
        Login or register user via OAuth provider.

        Flow:
        1. Check if OAuth account exists → Login existing user
        2. Check if user with email exists → Link OAuth account to user
        3. Create new user → Link OAuth account → Auto-assign trial

        Args:
            provider: OAuth provider (google, github, etc.)
            provider_account_id: Provider's unique ID for this account
            provider_email: Email from provider
            provider_name: Full name from provider
            provider_avatar_url: Avatar URL from provider
            provider_username: Username from provider
            access_token: OAuth access token
            refresh_token: OAuth refresh token
            token_expires_at: When the access token expires

        Returns:
            Tuple of (User object, tokens dict with access_token, refresh_token, token_type, and
            is_new_user: whether this call created the account, step 3, so the dashboard counts
            a sign-up only then)

        Raises:
            RextAuthenticationException: If OAuth flow fails
        """
        is_new_user = False
        # Check if this OAuth account already exists
        result = await self.db.execute(
            select(OAuthAccount)
            .options(
                selectinload(OAuthAccount.user)
            )  # Eagerly load user to avoid async lazy loading
            .where(
                OAuthAccount.provider == provider,
                OAuthAccount.provider_account_id == provider_account_id,
            )
        )
        oauth_account = result.scalar_one_or_none()

        if oauth_account:
            # OAuth account exists - login existing user
            user = oauth_account.user

            # Update OAuth account info
            oauth_account.provider_account_email = provider_email
            oauth_account.provider_username = provider_username
            oauth_account.provider_avatar_url = provider_avatar_url
            oauth_account.access_token = access_token
            oauth_account.refresh_token = refresh_token
            oauth_account.token_expires_at = token_expires_at
            oauth_account.last_used_at = datetime.now(timezone.utc)
            await self.db.flush()

            # Update user's last login
            user.last_login_at = datetime.now(timezone.utc)
            user.login_count = (user.login_count or 0) + 1
            await self.db.flush()

            logger.info(
                f"OAuth login successful for existing user: {user.id}",
                extra={"provider": provider, "email": provider_email},
            )

        else:
            if not email_verified:
                # Nothing is linked or opened on an address its provider has not confirmed
                # belongs to this account: an existing user with that address is someone else
                # until the provider says otherwise.
                raise RextAuthenticationException(
                    message=(
                        "The provider has not confirmed this email address, so it can't be used "
                        "to sign in here yet. Confirm it with the provider, or sign in with your "
                        "email and password."
                    )
                )
            # OAuth account doesn't exist - check if user with email exists. An address is the
            # same in any case: "Ana@example.com" registered by hand is this person too.
            result = await self.db.execute(
                select(Users)
                .where(func.lower(Users.email) == provider_email.lower())
                .order_by(Users.created_at)
            )
            user = result.scalars().first()

            if user:
                # User exists - link this OAuth account to their account
                logger.info(
                    f"Linking OAuth account to existing user: {user.id}",
                    extra={"provider": provider, "email": provider_email},
                )

                # Create OAuth account link
                oauth_account = OAuthAccount(
                    user_id=user.id,
                    provider=provider,
                    provider_account_id=provider_account_id,
                    provider_account_email=provider_email,
                    provider_username=provider_username,
                    provider_avatar_url=provider_avatar_url,
                    access_token=access_token,
                    refresh_token=refresh_token,
                    token_expires_at=token_expires_at,
                    created_at=datetime.now(timezone.utc),
                    last_used_at=datetime.now(timezone.utc),
                )
                self.db.add(oauth_account)
                await self.db.flush()

                # Update user's last login
                user.last_login_at = datetime.now(timezone.utc)
                user.login_count = (user.login_count or 0) + 1
                await self.db.flush()

            else:
                # User doesn't exist - create new user with OAuth account

                # Block disposable/temporary email providers before creating a new user
                if is_disposable_email(provider_email):
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail="Registrations from temporary or disposable email addresses are "
                        "not allowed. Please use a permanent email address.",
                    )

                logger.info(
                    "Creating new user with OAuth account",
                    extra={"provider": provider, "email": provider_email},
                )

                # Use provider_name as full_name
                full_name = provider_name or "User"

                # Create user (no password needed for OAuth-only users)
                user = Users(
                    full_name=full_name,
                    email=provider_email,
                    password_hash=None,  # Placeholder - OAuth users don't need password
                    email_verified=True,  # OAuth email is pre-verified
                    email_verified_at=datetime.now(timezone.utc),
                    avatar_url=provider_avatar_url,
                    created_at=datetime.now(timezone.utc),
                )
                self.db.add(user)
                await self.db.flush()
                is_new_user = True

                # No global role assignment: accounts no longer receive the
                # platform 'user' role. Workspace-scoped roles are granted when
                # the user creates or is invited to a workspace.

                # Create OAuth account link
                oauth_account = OAuthAccount(
                    user_id=user.id,
                    provider=provider,
                    provider_account_id=provider_account_id,
                    provider_account_email=provider_email,
                    provider_username=provider_username,
                    provider_avatar_url=provider_avatar_url,
                    access_token=access_token,
                    refresh_token=refresh_token,
                    token_expires_at=token_expires_at,
                    created_at=datetime.now(timezone.utc),
                    last_used_at=datetime.now(timezone.utc),
                )
                self.db.add(oauth_account)
                await self.db.flush()

                # Auto-assign trial subscription
                trial_plan = await self._get_trial_plan()
                if trial_plan:
                    trial_start = datetime.now(timezone.utc)
                    trial_end = trial_start + timedelta(days=TRIAL_DURATION_DAYS)

                    trial_subscription = UserSubscription(
                        user_id=user.id,
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
                            user.id, trial_plan.credits_per_month
                        )

                logger.info(
                    f"New user created via OAuth: {user.id}",
                    extra={"provider": provider, "email": provider_email},
                )

        # Generate JWT tokens
        # Explicitly query user roles to avoid lazy loading in async context.
        # Regular accounts may have no global role at all (the platform 'user'
        # role has been removed); workspace-scoped roles still apply.
        user_roles_result = await self.db.execute(
            select(UserRole)
            .options(selectinload(UserRole.role))
            .where(UserRole.user_id == user.id)
            .where(UserRole.is_primary.is_(True))
        )
        user_roles = user_roles_result.scalars().all()
        role_names = [ur.role.name for ur in user_roles]

        result = await self.db.execute(
            select(Permission.name)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .join(UserRole, UserRole.role_id == RolePermission.role_id)
            .where(UserRole.user_id == user.id)
            .where(UserRole.workspace_id.is_(None))
            .distinct()
        )
        permissions = [row[0] for row in result.all()]

        session_id = uuid4()
        token_data = {
            "id": str(user.id),
            "email": user.email,
            "roles": role_names,
            "permissions": permissions,
            "session_id": str(session_id),
            "session_kind": "user",
        }

        access_token = create_access_token(data=token_data)
        refresh_token = create_refresh_token(data=token_data)
        access_payload = decode_and_verify_token(access_token)
        refresh_payload = verify_refresh_token(refresh_token)
        now = datetime.now(timezone.utc)
        self.db.add(
            UserSession(
                id=session_id,
                user_id=user.id,
                jti=access_payload["jti"],
                device_name=f"{provider.title()} OAuth",
                device_type="oauth",
                user_agent="OAuth login",
                ip_address="Unknown",
                is_active=True,
                created_at=now,
                last_activity_at=now,
                expires_at=datetime.fromtimestamp(refresh_payload["exp"], tz=timezone.utc),
                session_metadata={"access_expires_at": int(access_payload["exp"])},
            )
        )
        await self.db.flush()

        tokens = {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "expires_in": get_settings().ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            "permissions": permissions,  # Include permissions for route response
            "roles": role_names,  # Include roles for route response
            "is_new_user": is_new_user,
        }

        return user, tokens

    async def link_oauth_account(
        self,
        user_id: UUID,
        provider: str,
        provider_account_id: str,
        provider_email: str,
        provider_username: Optional[str] = None,
        provider_avatar_url: Optional[str] = None,
        access_token: Optional[str] = None,
        refresh_token: Optional[str] = None,
        token_expires_at: Optional[datetime] = None,
    ) -> OAuthAccount:
        """
        Link an OAuth account to an existing user.

        Args:
            user_id: User UUID
            provider: OAuth provider
            provider_account_id: Provider's unique ID
            provider_email: Email from provider
            provider_username: Username from provider
            provider_avatar_url: Avatar URL from provider
            access_token: OAuth access token
            refresh_token: OAuth refresh token
            token_expires_at: Token expiration

        Returns:
            OAuthAccount obj

        Raises:
            DuplicateResourceException: If OAuth account already linked to another user
            ResourceNotFoundException: If user not found
        """
        # Check if user exists
        result = await self.db.execute(select(Users).where(Users.id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            raise ResourceNotFoundException(resource_type="User", resource_id=str(user_id))

        # Check if this OAuth account is already linked to another user
        result = await self.db.execute(
            select(OAuthAccount).where(
                OAuthAccount.provider == provider,
                OAuthAccount.provider_account_id == provider_account_id,
            )
        )
        existing_oauth = result.scalar_one_or_none()

        if existing_oauth:
            if existing_oauth.user_id != user_id:
                raise DuplicateResourceException(
                    message=f"This {provider} account is already linked to another user",
                    resource_type="oauth_account",
                    conflicting_field=f"{provider}_account_id",
                    conflicting_value=provider_account_id,
                )
            # Already linked to this user - update and return
            existing_oauth.provider_account_email = provider_email
            existing_oauth.provider_username = provider_username
            existing_oauth.provider_avatar_url = provider_avatar_url
            existing_oauth.access_token = access_token
            existing_oauth.refresh_token = refresh_token
            existing_oauth.token_expires_at = token_expires_at
            existing_oauth.updated_at = datetime.now(timezone.utc)
            await self.db.flush()
            return existing_oauth

        # Create new OAuth account link
        oauth_account = OAuthAccount(
            user_id=user_id,
            provider=provider,
            provider_account_id=provider_account_id,
            provider_account_email=provider_email,
            provider_username=provider_username,
            provider_avatar_url=provider_avatar_url,
            access_token=access_token,
            refresh_token=refresh_token,
            token_expires_at=token_expires_at,
            created_at=datetime.now(timezone.utc),
        )
        self.db.add(oauth_account)
        await self.db.flush()

        logger.info(
            f"OAuth account linked: {provider} for user {user_id}",
            extra={"provider": provider, "user_id": str(user_id)},
        )

        return oauth_account

    async def unlink_oauth_account(self, user_id: UUID, provider: str) -> None:
        """
        Unlink an OAuth account from a user.

        Args:
            user_id: User UUID
            provider: OAuth provider to unlink

        Raises:
            ResourceNotFoundException: If OAuth account not found
        """
        result = await self.db.execute(
            select(OAuthAccount).where(
                OAuthAccount.user_id == user_id, OAuthAccount.provider == provider
            )
        )
        oauth_account = result.scalar_one_or_none()

        if not oauth_account:
            raise ResourceNotFoundException(
                resource_type="OAuthAccount", resource_id=f"{user_id}:{provider}"
            )

        await self.db.delete(oauth_account)
        await self.db.flush()

        logger.info(
            f"OAuth account unlinked: {provider} from user {user_id}",
            extra={"provider": provider, "user_id": str(user_id)},
        )

    async def get_user_oauth_accounts(self, user_id: UUID) -> List[OAuthAccount]:
        """
        Get all OAuth accounts linked to a user.

        Args:
            user_id: User UUID

        Returns:
            List of OAuthAccount objects
        """
        result = await self.db.execute(select(OAuthAccount).where(OAuthAccount.user_id == user_id))
        return result.scalars().all()

    # ========================================================================
    # Private Helper Methods
    # ========================================================================

    async def _get_trial_plan(self) -> Optional[SubscriptionPlan]:
        """Get trial subscription plan."""
        result = await self.db.execute(
            select(SubscriptionPlan).where(
                SubscriptionPlan.name == "trial", SubscriptionPlan.is_active.is_(True)
            )
        )
        trial_plan = result.scalar_one_or_none()

        if not trial_plan:
            logger.warning("Trial subscription plan not found in database")

        return trial_plan
