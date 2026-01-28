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

from typing import Tuple, Dict, Any, Optional
from uuid import UUID
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.api.models.user_models.users import Users
from src.api.models.user_models.oauth_accounts import OAuthAccount
from src.api.models.user_models.roles import Role
from src.api.models.user_models.user_roles import UserRole
from src.api.models.user_models.permissions import Permission
from src.api.models.user_models.role_permissions import RolePermission
from src.api.models.subscription_models.plans import SubscriptionPlan
from src.api.models.subscription_models.subscriptions import (
    UserSubscription,
    SubscriptionStatus,
    BillingPeriod
)
from src.api.security.token_utils import (
    create_access_token,
    create_refresh_token,
)
from src.utils.logger import logger
from src.api.middleware.exceptions import (
    DuplicateResourceException,
    RextAuthenticationException,
    ResourceNotFoundException
)


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
        token_expires_at: Optional[datetime] = None
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
            Tuple of (User object, tokens dict with access_token, refresh_token, token_type)

        Raises:
            RextAuthenticationException: If OAuth flow fails
        """
        # Check if this OAuth account already exists
        result = await self.db.execute(
            select(OAuthAccount)
            .options(selectinload(OAuthAccount.user))  # Eagerly load user to avoid async lazy loading
            .where(
                OAuthAccount.provider == provider,
                OAuthAccount.provider_account_id == provider_account_id
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
            oauth_account.last_used_at = datetime.utcnow()
            await self.db.flush()

            # Update user's last login
            user.last_login_at = datetime.utcnow()
            user.login_count = (user.login_count or 0) + 1
            await self.db.flush()

            logger.info(
                f"OAuth login successful for existing user: {user.id}",
                extra={"provider": provider, "email": provider_email}
            )

        else:
            # OAuth account doesn't exist - check if user with email exists
            result = await self.db.execute(
                select(Users).where(Users.email == provider_email)
            )
            user = result.scalar_one_or_none()

            if user:
                # User exists - link this OAuth account to their account
                logger.info(
                    f"Linking OAuth account to existing user: {user.id}",
                    extra={"provider": provider, "email": provider_email}
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
                    created_at=datetime.utcnow(),
                    last_used_at=datetime.utcnow()
                )
                self.db.add(oauth_account)
                await self.db.flush()

                # Update user's last login
                user.last_login_at = datetime.utcnow()
                user.login_count = (user.login_count or 0) + 1
                await self.db.flush()

            else:
                # User doesn't exist - create new user with OAuth account
                logger.info(
                    f"Creating new user with OAuth account",
                    extra={"provider": provider, "email": provider_email}
                )

                # Use provider_name as full_name
                full_name = provider_name or "User"

                # Create user (no password needed for OAuth-only users)
                user = Users(
                    full_name=full_name,
                    email=provider_email,
                    password_hash="oauth_no_password",  # Placeholder - OAuth users don't need password
                    email_verified=True,  # OAuth email is pre-verified
                    email_verified_at=datetime.utcnow(),
                    avatar_url=provider_avatar_url,
                    created_at=datetime.utcnow()
                )
                self.db.add(user)
                await self.db.flush()

                # Assign default 'user' role
                default_role = await self._get_or_create_default_role()
                user_role = UserRole(
                    user_id=user.id,
                    role_id=default_role.id,
                    workspace_id=None,
                    is_primary=True,
                    assigned_at=datetime.utcnow(),
                    assigned_by_user_id=user.id
                )
                self.db.add(user_role)
                await self.db.flush()

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
                    created_at=datetime.utcnow(),
                    last_used_at=datetime.utcnow()
                )
                self.db.add(oauth_account)
                await self.db.flush()

                # Auto-assign trial subscription
                trial_plan = await self._get_trial_plan()
                if trial_plan:
                    trial_start = datetime.utcnow()
                    trial_end = trial_start + timedelta(days=14)

                    trial_subscription = UserSubscription(
                        user_id=user.id,
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
                    f"New user created via OAuth: {user.id}",
                    extra={"provider": provider, "email": provider_email}
                )

        # Generate JWT tokens
        # Explicitly query user roles to avoid lazy loading in async context
        user_roles_result = await self.db.execute(
            select(UserRole)
            .options(selectinload(UserRole.role))
            .where(UserRole.user_id == user.id)
            .where(UserRole.is_primary == True)
        )
        user_roles = user_roles_result.scalars().all()
        role_names = [ur.role.name for ur in user_roles]

        result = await self.db.execute(
                select(Permission.name)
                .join(RolePermission, RolePermission.permission_id == Permission.id)
                .join(UserRole, UserRole.role_id == RolePermission.role_id)
                .where(UserRole.user_id == user.id)
                .where(UserRole.workspace_id == None)
                .distinct()
            )
        permissions = [row[0] for row in result.all()]

        token_data = {
            "id": str(user.id),
            "email": user.email,
            "roles": role_names,
            "permissions": permissions
        }

        access_token = create_access_token(data=token_data)
        refresh_token = create_refresh_token(data=token_data)

        tokens = {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "permissions": permissions,  # Include permissions for route response
            "roles": role_names  # Include roles for route response
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
        token_expires_at: Optional[datetime] = None
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
        result = await self.db.execute(
            select(Users).where(Users.id == user_id)
        )
        user = result.scalar_one_or_none()
        if not user:
            raise ResourceNotFoundException(
                resource_type="User",
                resource_id=str(user_id)
            )

        # Check if this OAuth account is already linked to another user
        result = await self.db.execute(
            select(OAuthAccount).where(
                OAuthAccount.provider == provider,
                OAuthAccount.provider_account_id == provider_account_id
            )
        )
        existing_oauth = result.scalar_one_or_none()

        if existing_oauth:
            if existing_oauth.user_id != user_id:
                raise DuplicateResourceException(
                    message=f"This {provider} account is already linked to another user",
                    resource_type="oauth_account",
                    conflicting_field=f"{provider}_account_id",
                    conflicting_value=provider_account_id
                )
            # Already linked to this user - update and return
            existing_oauth.provider_account_email = provider_email
            existing_oauth.provider_username = provider_username
            existing_oauth.provider_avatar_url = provider_avatar_url
            existing_oauth.access_token = access_token
            existing_oauth.refresh_token = refresh_token
            existing_oauth.token_expires_at = token_expires_at
            existing_oauth.updated_at = datetime.utcnow()
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
            created_at=datetime.utcnow()
        )
        self.db.add(oauth_account)
        await self.db.flush()

        logger.info(
            f"OAuth account linked: {provider} for user {user_id}",
            extra={"provider": provider, "user_id": str(user_id)}
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
                OAuthAccount.user_id == user_id,
                OAuthAccount.provider == provider
            )
        )
        oauth_account = result.scalar_one_or_none()

        if not oauth_account:
            raise ResourceNotFoundException(
                resource_type="OAuthAccount",
                resource_id=f"{user_id}:{provider}"
            )

        await self.db.delete(oauth_account)
        await self.db.flush()

        logger.info(
            f"OAuth account unlinked: {provider} from user {user_id}",
            extra={"provider": provider, "user_id": str(user_id)}
        )

    # ========================================================================
    # Private Helper Methods
    # ========================================================================

    async def _get_or_create_default_role(self) -> Role:
        """Get or create default 'user' role."""
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
        """Get trial subscription plan."""
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
