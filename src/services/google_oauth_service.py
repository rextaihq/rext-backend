"""
Google OAuth Service - OAuth 2.0 connection lifecycle for Search Console + GA4

Responsibilities:
- Build the Google consent URL (JWT-signed state, mirrors the Shopify
  install-state pattern in IntegrationService).
- Complete the OAuth callback and persist the workspace's GoogleIntegration.
- Provide a single, reused token-refresh path (get_valid_access_token) for
  both SearchConsoleService and GoogleAnalyticsService.
- Disconnect (revoke + deactivate).

Does NOT:
- Call the Search Console or GA4 APIs themselves (see the dedicated services).
- Handle HTTP requests/responses (that's routes).
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
from urllib.parse import urlencode, urlparse
import uuid

import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.config import settings
from src.api.middleware.exceptions import RextValidationException
from src.api.models.integrations.google_integration import GoogleIntegration
from src.utils.logger import logger
from src.web.google_oauth import GoogleOAuthClient

# Refresh proactively if the token expires within this many seconds
_TOKEN_REFRESH_BUFFER_SECONDS = 300


class GoogleOAuthService:
    """Service for the Google OAuth connection lifecycle."""

    def __init__(self, db: AsyncSession):
        self.db = db

    def _client(self) -> GoogleOAuthClient:
        return GoogleOAuthClient(
            client_id=settings.GOOGLE_CLIENT_ID,
            client_secret=settings.GOOGLE_CLIENT_SECRET,
        )

    # ------------------------------------------------------------------
    # State (CSRF-protected, carries workspace/user context through Google)
    # ------------------------------------------------------------------

    def _create_state(
        self, *, workspace_id: uuid.UUID, user_id: str, return_path: Optional[str]
    ) -> str:
        payload = {
            "workspace_id": str(workspace_id),
            "user_id": user_id,
            "return_path": return_path or settings.GOOGLE_INTEGRATION_RETURN_PATH,
            "exp": datetime.now(timezone.utc) + timedelta(minutes=15),
            "type": "google_oauth_state",
        }
        return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

    def decode_state(self, state: str) -> Dict[str, Any]:
        try:
            payload = jwt.decode(state, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        except jwt.PyJWTError as exc:
            raise RextValidationException(
                message="Invalid or expired Google authorization state."
            ) from exc

        if payload.get("type") != "google_oauth_state":
            raise RextValidationException(message="Invalid Google authorization state.")

        return payload

    # ------------------------------------------------------------------
    # Frontend redirect helpers
    # ------------------------------------------------------------------

    def _frontend_return_url(
        self, *, status: str, workspace_id: Optional[str] = None,
        return_path: Optional[str] = None, error: Optional[str] = None,
    ) -> str:
        base_frontend = settings.FRONTEND_URL.rstrip("/")
        target_path = self._normalize_frontend_return_path(return_path)

        params = {"provider": "google", "status": status}
        if workspace_id:
            params["workspace_id"] = workspace_id
        if error:
            params["error"] = error

        return f"{base_frontend}{target_path}?{urlencode(params)}"

    def _normalize_frontend_return_path(self, return_path: Optional[str]) -> str:
        fallback_path = settings.GOOGLE_INTEGRATION_RETURN_PATH.strip() or "/"
        if not fallback_path.startswith("/"):
            fallback_path = f"/{fallback_path}"

        raw_value = (return_path or "").strip()
        if not raw_value:
            return fallback_path

        parsed = urlparse(raw_value)
        if parsed.scheme and parsed.netloc:
            frontend = urlparse(settings.FRONTEND_URL)
            same_origin = (
                parsed.scheme.lower() == frontend.scheme.lower()
                and parsed.netloc.lower() == frontend.netloc.lower()
            )
            if not same_origin:
                return fallback_path
            path = parsed.path or "/"
            if not path.startswith("/"):
                path = f"/{path}"
            if parsed.query:
                path = f"{path}?{parsed.query}"
            return path

        if raw_value.startswith("/"):
            return raw_value
        return f"/{raw_value}"

    def build_error_redirect(
        self, *, message: str, return_path: Optional[str] = None,
        workspace_id: Optional[str] = None,
    ) -> str:
        return self._frontend_return_url(
            status="error", workspace_id=workspace_id, return_path=return_path, error=message
        )

    # ------------------------------------------------------------------
    # OAuth flow
    # ------------------------------------------------------------------

    def build_authorization_url(
        self, *, workspace_id: uuid.UUID, user_id: str, callback_url: str,
        return_path: Optional[str] = None,
    ) -> str:
        """Build the Google OAuth consent URL for a workspace."""
        if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
            raise RextValidationException(
                message="Google OAuth credentials are not configured on the backend."
            )

        state = self._create_state(
            workspace_id=workspace_id, user_id=user_id, return_path=return_path
        )
        return self._client().build_authorization_url(
            redirect_uri=callback_url,
            state=state,
            scopes=settings.google_oauth_scopes_list,
        )

    async def complete_oauth(self, *, query_params: Dict[str, str], callback_url: str) -> str:
        """
        Complete the Google OAuth callback and return the frontend redirect URL.
        """
        if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
            raise RextValidationException(
                message="Google OAuth credentials are not configured on the backend."
            )

        error = query_params.get("error")
        if error:
            raise RextValidationException(message=f"Google authorization was not completed: {error}")

        state = query_params.get("state")
        code = query_params.get("code")
        if not state or not code:
            raise RextValidationException(message="Missing required Google callback parameters.")

        state_payload = self.decode_state(state)
        workspace_id = uuid.UUID(state_payload["workspace_id"])
        user_id = uuid.UUID(state_payload["user_id"])

        token_payload = await self._client().exchange_code(code=code, redirect_uri=callback_url)
        access_token = token_payload.get("access_token")
        refresh_token = token_payload.get("refresh_token")
        expires_in = token_payload.get("expires_in", 3600)
        granted_scopes = token_payload.get("scope", settings.GOOGLE_OAUTH_SCOPES)

        if not access_token:
            raise RextValidationException(message="Google did not return an access token.")

        integration = await self._get_workspace_integration(workspace_id)

        if not refresh_token and integration and integration.refresh_token:
            # Google only issues a refresh_token on first consent; keep the existing one
            # on reconnects (access_type=offline + prompt=consent should prevent this,
            # but don't drop a working refresh_token if Google omits it anyway).
            refresh_token = integration.refresh_token

        if not refresh_token:
            raise RextValidationException(
                message=(
                    "Google did not return a refresh token. Please disconnect and try "
                    "connecting again, making sure to approve all requested permissions."
                )
            )

        userinfo = await self._client().get_userinfo(access_token)
        token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)

        if integration:
            integration.access_token = access_token
            integration.refresh_token = refresh_token
            integration.token_expires_at = token_expires_at
            integration.scopes = granted_scopes
            integration.google_account_email = userinfo.get("email") or integration.google_account_email
            integration.connected_by_user_id = user_id
            integration.is_active = True
            integration.last_refreshed_at = datetime.now(timezone.utc)
            integration.deleted_at = None
        else:
            integration = GoogleIntegration(
                workspace_id=workspace_id,
                access_token=access_token,
                refresh_token=refresh_token,
                token_expires_at=token_expires_at,
                scopes=granted_scopes,
                google_account_email=userinfo.get("email"),
                connected_by_user_id=user_id,
                is_active=True,
                last_refreshed_at=datetime.now(timezone.utc),
            )
            self.db.add(integration)

        await self.db.flush()
        await self.db.commit()

        logger.info(
            "Google integration connected",
            extra={"workspace_id": str(workspace_id), "email": integration.google_account_email},
        )

        return self._frontend_return_url(
            status="connected",
            workspace_id=str(workspace_id),
            return_path=state_payload.get("return_path"),
        )

    # ------------------------------------------------------------------
    # Lookup + token refresh
    # ------------------------------------------------------------------

    async def _get_workspace_integration(
        self, workspace_id: uuid.UUID
    ) -> Optional[GoogleIntegration]:
        result = await self.db.execute(
            select(GoogleIntegration)
            .where(
                GoogleIntegration.workspace_id == workspace_id,
                GoogleIntegration.deleted_at.is_(None),
            )
            .order_by(GoogleIntegration.updated_at.desc(), GoogleIntegration.created_at.desc())
        )
        return result.scalars().first()

    async def get_integration(self, workspace_id: uuid.UUID) -> Optional[GoogleIntegration]:
        """Return the workspace's Google connection, active or not (None if never connected)."""
        return await self._get_workspace_integration(workspace_id)

    async def get_active_integration(self, workspace_id: uuid.UUID) -> Optional[GoogleIntegration]:
        integration = await self._get_workspace_integration(workspace_id)
        if integration and integration.is_active:
            return integration
        return None

    async def get_valid_access_token(self, integration: GoogleIntegration) -> str:
        """
        Return a usable access token, refreshing it first if it's expired or
        close to expiring. Persists the refreshed token. This is the single
        reused refresh path for both SearchConsoleService and
        GoogleAnalyticsService.
        """
        now = datetime.now(timezone.utc)
        expires_at = integration.token_expires_at
        needs_refresh = (
            not integration.access_token
            or not expires_at
            or expires_at <= now + timedelta(seconds=_TOKEN_REFRESH_BUFFER_SECONDS)
        )

        if not needs_refresh:
            return integration.access_token

        if not integration.refresh_token:
            integration.is_active = False
            await self.db.flush()
            raise RextValidationException(
                message="Google connection has no refresh token; please reconnect."
            )

        try:
            token_payload = await self._client().refresh_access_token(integration.refresh_token)
        except Exception:
            # Refresh itself failed (e.g. token revoked externally) — deactivate so the
            # scheduler/UI can surface a clear "reconnect required" state instead of
            # retrying a doomed refresh on every sync cycle.
            integration.is_active = False
            await self.db.flush()
            raise

        integration.access_token = token_payload.get("access_token")
        expires_in = token_payload.get("expires_in", 3600)
        integration.token_expires_at = now + timedelta(seconds=expires_in)
        integration.last_refreshed_at = now
        await self.db.flush()

        return integration.access_token

    async def disconnect(self, workspace_id: uuid.UUID) -> None:
        """Revoke the Google connection (best effort) and deactivate it."""
        integration = await self._get_workspace_integration(workspace_id)
        if not integration:
            return

        client = self._client()
        if integration.refresh_token:
            await client.revoke_token(integration.refresh_token)
        elif integration.access_token:
            await client.revoke_token(integration.access_token)

        integration.is_active = False
        integration.soft_delete()
        await self.db.flush()

        logger.info("Google integration disconnected", extra={"workspace_id": str(workspace_id)})
