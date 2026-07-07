"""
Google OAuth 2.0 Client

Low-level httpx wrapper around Google's OAuth 2.0 endpoints (authorization
code exchange, refresh token, revoke, userinfo). No google-auth /
google-api-python-client dependency — plain REST calls, consistent with how
ShopifyConnector/WordPressPublisher are built in this project.
"""

import logging
from typing import Any, Dict, List
from urllib.parse import urlencode

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from src.api.middleware.exceptions import (
    ExternalServiceTimeoutException,
    RextExternalServiceException,
)

logger = logging.getLogger(__name__)

GOOGLE_AUTH_BASE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_REVOKE_URL = "https://oauth2.googleapis.com/revoke"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"

_TIMEOUT = 20.0


class GoogleOAuthClient:
    """OAuth 2.0 client for Google's authorization-code + refresh-token flow."""

    def __init__(self, client_id: str, client_secret: str):
        if not client_id or not client_secret:
            raise RextExternalServiceException(
                message="Google OAuth client ID/secret are not configured on the backend.",
                service_name="Google OAuth",
            )
        self.client_id = client_id
        self.client_secret = client_secret

    def build_authorization_url(self, redirect_uri: str, state: str, scopes: List[str]) -> str:
        """
        Build the Google consent screen URL.

        access_type=offline + prompt=consent guarantee a refresh_token is
        returned even if the user has granted consent before — Google only
        issues one on the very first consent otherwise.
        """
        params = {
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": " ".join(scopes),
            "access_type": "offline",
            "prompt": "consent",
            "include_granted_scopes": "true",
            "state": state,
        }
        return f"{GOOGLE_AUTH_BASE_URL}?{urlencode(params)}"

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=1, max=5),
        retry=retry_if_exception_type((httpx.NetworkError, httpx.TimeoutException)),
        reraise=True,
    )
    async def exchange_code(self, code: str, redirect_uri: str) -> Dict[str, Any]:
        """Exchange an authorization code for an access_token + refresh_token."""
        return await self._post_token({
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        })

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=1, max=5),
        retry=retry_if_exception_type((httpx.NetworkError, httpx.TimeoutException)),
        reraise=True,
    )
    async def refresh_access_token(self, refresh_token: str) -> Dict[str, Any]:
        """Exchange a refresh token for a new access token."""
        return await self._post_token({
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        })

    async def _post_token(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                response = await client.post(GOOGLE_TOKEN_URL, data=payload)

            if response.status_code != 200:
                error_body = response.text[:300]
                logger.error(f"Google token endpoint error {response.status_code}: {error_body}")
                raise RextExternalServiceException(
                    message=(
                        "Failed to authenticate with Google. The authorization may have "
                        "expired or been revoked."
                    ),
                    service_name="Google OAuth",
                    service_error=error_body,
                )

            return response.json()

        except (RextExternalServiceException, ExternalServiceTimeoutException):
            raise
        except httpx.TimeoutException:
            raise ExternalServiceTimeoutException(
                service_name="Google OAuth", timeout_seconds=int(_TIMEOUT)
            )
        except httpx.HTTPError as exc:
            logger.error(f"HTTP error calling Google token endpoint: {exc}")
            raise RextExternalServiceException(
                message="Unable to reach Google's authentication service.",
                service_name="Google OAuth",
            )

    async def revoke_token(self, token: str) -> None:
        """Best-effort revoke of an access or refresh token. Never raises."""
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                response = await client.post(
                    GOOGLE_REVOKE_URL,
                    params={"token": token},
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
            if response.status_code not in (200, 400):
                logger.warning(
                    f"Google token revoke returned {response.status_code}: {response.text[:200]}"
                )
        except Exception as exc:
            logger.warning(f"Failed to revoke Google token (non-fatal): {exc}")

    async def get_userinfo(self, access_token: str) -> Dict[str, Any]:
        """Fetch basic profile info (email) for the connected Google account. Never raises."""
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                response = await client.get(
                    GOOGLE_USERINFO_URL,
                    headers={"Authorization": f"Bearer {access_token}"},
                )
            if response.status_code != 200:
                logger.warning(f"Failed to fetch Google userinfo: {response.status_code}")
                return {}
            return response.json()
        except Exception as exc:
            logger.warning(f"Failed to fetch Google userinfo (non-fatal): {exc}")
            return {}
