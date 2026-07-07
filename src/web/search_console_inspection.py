"""
Google Search Console URL Inspection API Client

Low-level httpx wrapper for the URL Inspection API
(https://searchconsole.googleapis.com/v1/urlInspection/index:inspect).

This is a distinct API surface from Search Analytics (src/web/search_console.py):
one call per URL, no bulk endpoint, and Google enforces a per-property quota
(commonly ~2,000/day, ~600/min at time of writing — verify current limits in
the Search Console API quota dashboard, since Google can change these). Quota
management lives in src/utils/google_quota_limiter.py, not here — this client
only makes the call and reports 429s distinctly so callers can back off.
"""

import logging
from typing import Any, Dict

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

URL_INSPECTION_ENDPOINT = "https://searchconsole.googleapis.com/v1/urlInspection/index:inspect"
_TIMEOUT = 20.0


class GoogleQuotaExceededException(RextExternalServiceException):
    """Raised when Google returns 429 for the URL Inspection API."""

    def __init__(self):
        super().__init__(
            message="Search Console URL Inspection quota exceeded for this property.",
            service_name="Search Console URL Inspection",
        )


class URLInspectionClient:
    """URL Inspection API client, scoped to a single access token."""

    def __init__(self, access_token: str):
        self.access_token = access_token
        self._client = httpx.AsyncClient(
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            timeout=_TIMEOUT,
        )

    async def __aenter__(self) -> "URLInspectionClient":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()

    async def close(self) -> None:
        await self._client.aclose()

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=1, max=5),
        retry=retry_if_exception_type((httpx.NetworkError, httpx.TimeoutException)),
        reraise=True,
    )
    async def inspect_url(self, site_url: str, inspection_url: str) -> Dict[str, Any]:
        """
        Inspect a single URL's index status.

        ``site_url`` is the verified Search Console property; ``inspection_url``
        is the full published article URL.
        """
        payload = {"inspectionUrl": inspection_url, "siteUrl": site_url}

        try:
            response = await self._client.post(URL_INSPECTION_ENDPOINT, json=payload)

            if response.status_code == 401:
                raise RextExternalServiceException(
                    message="Google Search Console authorization is invalid or expired.",
                    service_name="Search Console URL Inspection",
                )
            if response.status_code == 403:
                raise RextExternalServiceException(
                    message=(
                        "This Google account does not have access to the requested "
                        "Search Console property."
                    ),
                    service_name="Search Console URL Inspection",
                )
            if response.status_code == 429:
                raise GoogleQuotaExceededException()
            if response.status_code >= 400:
                raise RextExternalServiceException(
                    message=(
                        f"URL Inspection API returned unexpected status "
                        f"{response.status_code}: {response.text[:200]}"
                    ),
                    service_name="Search Console URL Inspection",
                )

            return response.json()

        except (RextExternalServiceException, ExternalServiceTimeoutException):
            raise
        except httpx.TimeoutException:
            raise ExternalServiceTimeoutException(
                service_name="Search Console URL Inspection", timeout_seconds=int(_TIMEOUT)
            )
        except httpx.HTTPError as exc:
            logger.error(f"HTTP error calling URL Inspection API: {exc}")
            raise RextExternalServiceException(
                message="Unable to reach Google Search Console.",
                service_name="Search Console URL Inspection",
            )
