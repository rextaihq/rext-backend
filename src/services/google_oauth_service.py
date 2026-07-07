"""
Google OAuth Service

Handles Google OAuth 2.0 authentication for GSC and GA4 integration.
Manages token storage, refresh, and state signing using JWT.

Follows patterns from existing Shopify integration OAuth flow.
"""

import httpx
from urllib.parse import urlencode
import jwt
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.api.config import settings
from src.api.models.user_models.oauth_accounts import OAuthAccount
from src.api.models.integrations.workspace_google_connection import WorkspaceGoogleConnection
from src.api.middleware.exceptions import (
    RextAuthenticationException,
    ResourceNotFoundException,
)
from src.utils.logger import logger


class GoogleOAuthService:
    """
    Service for Google OAuth authentication and token management.
    
    Handles OAuth flow for combined GSC and GA4 access.
    """

    # Google OAuth endpoints
    GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
    GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
    
    # Required OAuth scopes for GSC and GA4
    SCOPES = [
        "https://www.googleapis.com/auth/webmasters.readonly",  # GSC
        "https://www.googleapis.com/auth/analytics.readonly",  # GA4
        "https://www.googleapis.com/auth/userinfo.email",  # Get user email
    ]

    def __init__(self, db: AsyncSession):
        """
        Initialize GoogleOAuthService.

        Args:
            db: Async database session
        """
        self.db = db

    async def build_oauth_url(
        self,
        *,
        workspace_id: UUID,
        user_id: UUID,
        return_path: Optional[str] = None,
    ) -> str:
        """
        Build Google OAuth authorization URL with signed state parameter.
        
        The state parameter contains:
        - workspace_id: For linking OAuth account to workspace
        - user_id: For linking OAuth account to user
        - return_path: Frontend path to redirect after OAuth completes
        - exp: Expiration timestamp (15 minutes)
        - type: 'google_oauth_state' for validation

        Args:
            workspace_id: Workspace UUID
            user_id: User UUID initiating OAuth
            return_path: Optional frontend path to return to after OAuth

        Returns:
            Google OAuth authorization URL

        Raises:
            ValueError: If GOOGLE_CLIENT_ID not configured
        """
        if not settings.GOOGLE_CLIENT_ID:
            raise ValueError("GOOGLE_CLIENT_ID not configured in settings")

        # Build callback URL
        if settings.BACKEND_URL:
            callback_url = f"{settings.BACKEND_URL.rstrip('/')}{settings.GOOGLE_OAUTH_REDIRECT_PATH}"
        else:
            # Fallback for local development — use localhost, not 0.0.0.0
            callback_url = f"http://localhost:{settings.PORT}{settings.GOOGLE_OAUTH_REDIRECT_PATH}"

        # Create JWT-signed state parameter
        state_payload = {
            "workspace_id": str(workspace_id),
            "user_id": str(user_id),
            "return_path": return_path or settings.GOOGLE_INTEGRATION_RETURN_PATH,
            "exp": datetime.now(timezone.utc) + timedelta(minutes=15),
            "type": "google_oauth_state",
        }
        state = jwt.encode(
            state_payload,
            settings.SECRET_KEY,
            algorithm=settings.ALGORITHM
        )

        # Build OAuth URL
        params = {
            "client_id": settings.GOOGLE_CLIENT_ID,
            "redirect_uri": callback_url,
            "response_type": "code",
            "scope": " ".join(self.SCOPES),
            "state": state,
            "access_type": "offline",  # Request refresh token
            "prompt": "consent",  # Force consent to get refresh token
        }

        oauth_url = f"{self.GOOGLE_AUTH_URL}?{urlencode(params)}"

        logger.info(
            f"Built Google OAuth URL for workspace {workspace_id}",
            extra={"workspace_id": str(workspace_id), "user_id": str(user_id)}
        )

        return oauth_url

    async def handle_oauth_callback(
        self,
        *,
        code: str,
        state: str,
    ) -> Dict[str, Any]:
        """
        Handle Google OAuth callback.
        
        Flow:
        1. Validate and decode state parameter
        2. Exchange authorization code for tokens
        3. Get user email from Google
        4. Store tokens in OAuthAccount
        5. Return workspace_id and return_path for redirect

        Args:
            code: Authorization code from Google
            state: JWT-signed state parameter

        Returns:
            Dict with workspace_id, user_id, oauth_account_id, return_path

        Raises:
            RextAuthenticationException: If OAuth validation fails
        """
        # Validate and decode state
        try:
            state_data = jwt.decode(
                state,
                settings.SECRET_KEY,
                algorithms=[settings.ALGORITHM]
            )
            
            if state_data.get("type") != "google_oauth_state":
                raise RextAuthenticationException("Invalid OAuth state type")
            
            workspace_id = UUID(state_data["workspace_id"])
            user_id = UUID(state_data["user_id"])
            return_path = state_data.get("return_path", settings.GOOGLE_INTEGRATION_RETURN_PATH)
            
        except jwt.ExpiredSignatureError:
            raise RextAuthenticationException("OAuth state expired. Please try again.")
        except jwt.InvalidTokenError as e:
            raise RextAuthenticationException(f"Invalid OAuth state: {str(e)}")
        except (KeyError, ValueError) as e:
            raise RextAuthenticationException(f"Invalid OAuth state data: {str(e)}")

        # Build callback URL
        if settings.BACKEND_URL:
            redirect_uri = f"{settings.BACKEND_URL.rstrip('/')}{settings.GOOGLE_OAUTH_REDIRECT_PATH}"
        else:
            # Fallback for local development — use localhost, not 0.0.0.0
            redirect_uri = f"http://localhost:{settings.PORT}{settings.GOOGLE_OAUTH_REDIRECT_PATH}"

        # Exchange code for tokens
        try:
            async with httpx.AsyncClient() as client:
                token_response = await client.post(
                    self.GOOGLE_TOKEN_URL,
                    data={
                        "code": code,
                        "client_id": settings.GOOGLE_CLIENT_ID,
                        "client_secret": settings.GOOGLE_CLIENT_SECRET,
                        "redirect_uri": redirect_uri,
                        "grant_type": "authorization_code",
                    },
                    timeout=30.0,
                )
                token_response.raise_for_status()
                tokens = token_response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"Google token exchange failed: {e.response.text}")
            raise RextAuthenticationException(f"Failed to exchange authorization code: {e}")
        except Exception as e:
            logger.error(f"Google OAuth error: {str(e)}")
            raise RextAuthenticationException(f"OAuth error: {str(e)}")

        access_token = tokens.get("access_token")
        refresh_token = tokens.get("refresh_token")
        expires_in = tokens.get("expires_in", 3600)
        
        if not access_token:
            raise RextAuthenticationException("No access token received from Google")

        # Calculate token expiration
        token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

        # Get user email from Google
        try:
            async with httpx.AsyncClient() as client:
                userinfo_response = await client.get(
                    "https://www.googleapis.com/oauth2/v2/userinfo",
                    headers={"Authorization": f"Bearer {access_token}"},
                    timeout=30.0,
                )
                userinfo_response.raise_for_status()
                userinfo = userinfo_response.json()
                provider_email = userinfo.get("email")
                provider_account_id = userinfo.get("id")
        except Exception as e:
            logger.error(f"Failed to get user info from Google: {str(e)}")
            raise RextAuthenticationException("Failed to get user information from Google")

        if not provider_email or not provider_account_id:
            raise RextAuthenticationException("Google did not provide required user information")

        # Store or update OAuth account
        result = await self.db.execute(
            select(OAuthAccount).where(
                OAuthAccount.user_id == user_id,
                OAuthAccount.provider == "google"
            )
        )
        oauth_account = result.scalar_one_or_none()

        if oauth_account:
            # Update existing OAuth account
            oauth_account.provider_account_id = provider_account_id
            oauth_account.provider_account_email = provider_email
            oauth_account.access_token = access_token
            oauth_account.refresh_token = refresh_token or oauth_account.refresh_token
            oauth_account.token_expires_at = token_expires_at
            oauth_account.updated_at = datetime.now(timezone.utc)
            oauth_account.last_used_at = datetime.now(timezone.utc)
        else:
            # Create new OAuth account
            oauth_account = OAuthAccount(
                user_id=user_id,
                provider="google",
                provider_account_id=provider_account_id,
                provider_account_email=provider_email,
                access_token=access_token,
                refresh_token=refresh_token,
                token_expires_at=token_expires_at,
                created_at=datetime.now(timezone.utc),
                last_used_at=datetime.now(timezone.utc),
            )
            self.db.add(oauth_account)

        await self.db.flush()

        logger.info(
            f"Google OAuth tokens stored for user {user_id}",
            extra={
                "user_id": str(user_id),
                "workspace_id": str(workspace_id),
                "provider_email": provider_email,
            }
        )

        return {
            "workspace_id": workspace_id,
            "user_id": user_id,
            "oauth_account_id": oauth_account.id,
            "return_path": return_path,
            "provider_email": provider_email,
        }

    async def refresh_token(
        self,
        oauth_account: OAuthAccount,
    ) -> OAuthAccount:
        """
        Refresh expired Google OAuth access token.

        Args:
            oauth_account: OAuthAccount with refresh_token

        Returns:
            Updated OAuthAccount

        Raises:
            RextAuthenticationException: If token refresh fails
        """
        if not oauth_account.refresh_token:
            raise RextAuthenticationException(
                "No refresh token available for Google OAuth account"
            )

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.GOOGLE_TOKEN_URL,
                    data={
                        "client_id": settings.GOOGLE_CLIENT_ID,
                        "client_secret": settings.GOOGLE_CLIENT_SECRET,
                        "refresh_token": oauth_account.refresh_token,
                        "grant_type": "refresh_token",
                    },
                    timeout=30.0,
                )
                response.raise_for_status()
                tokens = response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"Google token refresh failed: {e.response.text}")
            raise RextAuthenticationException(
                "Failed to refresh Google access token. Please reconnect your account."
            )
        except Exception as e:
            logger.error(f"Google token refresh error: {str(e)}")
            raise RextAuthenticationException(f"Token refresh error: {str(e)}")

        access_token = tokens.get("access_token")
        expires_in = tokens.get("expires_in", 3600)
        new_refresh_token = tokens.get("refresh_token")  # Google may rotate refresh token

        if not access_token:
            raise RextAuthenticationException("No access token received during refresh")

        # Update OAuth account
        oauth_account.access_token = access_token
        if new_refresh_token:
            oauth_account.refresh_token = new_refresh_token
        oauth_account.token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
        oauth_account.updated_at = datetime.now(timezone.utc)

        await self.db.flush()

        logger.info(
            f"Refreshed Google OAuth token for user {oauth_account.user_id}",
            extra={"user_id": str(oauth_account.user_id)}
        )

        return oauth_account

    async def get_valid_token(
        self,
        workspace_id: UUID,
    ) -> str:
        """
        Get a valid Google OAuth access token for a workspace.
        
        Automatically refreshes the token if it's expired or about to expire.

        Args:
            workspace_id: Workspace UUID

        Returns:
            Valid access token

        Raises:
            ResourceNotFoundException: If no Google connection exists
            RextAuthenticationException: If token refresh fails
        """
        # Get workspace Google connection
        result = await self.db.execute(
            select(WorkspaceGoogleConnection)
            .options(selectinload(WorkspaceGoogleConnection.oauth_account))
            .where(WorkspaceGoogleConnection.workspace_id == workspace_id)
        )
        connection = result.scalar_one_or_none()

        if not connection or not connection.oauth_account:
            raise ResourceNotFoundException(
                resource_type="GoogleConnection",
                resource_id=str(workspace_id),
                message="No Google connection found for this workspace. Please connect your Google account."
            )

        oauth_account = connection.oauth_account

        # Check if token needs refresh (expired or expiring in next 5 minutes)
        now = datetime.now(timezone.utc)
        needs_refresh = (
            not oauth_account.token_expires_at or
            oauth_account.token_expires_at <= now + timedelta(minutes=5)
        )

        if needs_refresh:
            logger.info(f"Refreshing Google token for workspace {workspace_id}")
            oauth_account = await self.refresh_token(oauth_account)

        return oauth_account.access_token
