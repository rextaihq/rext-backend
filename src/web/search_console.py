"""
Google Search Console API Client

Low-level httpx wrapper for the Search Console API (webmasters/v3). Auth is
via a bearer access token supplied by the caller — this client does not
refresh or persist tokens itself (see GoogleOAuthService for that).
"""

import logging
from datetime import date
from typing import Any, Dict, List
from urllib.parse import quote

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

SEARCH_CONSOLE_BASE_URL = "https://searchconsole.googleapis.com/webmasters/v3"
_TIMEOUT = 20.0


class SearchConsoleClient:
    """Search Console API client, scoped to a single access token."""

    def __init__(self, access_token: str):
        self.access_token = access_token
        self._client = httpx.AsyncClient(
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            timeout=_TIMEOUT,
        )

    async def __aenter__(self) -> "SearchConsoleClient":
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
    async def list_sites(self) -> List[Dict[str, Any]]:
        """List verified Search Console properties for the connected account."""
        endpoint = f"{SEARCH_CONSOLE_BASE_URL}/sites"
        response = await self._request("GET", endpoint)
        return response.json().get("siteEntry", [])

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_exponential(multiplier=1, min=1, max=5),
        retry=retry_if_exception_type((httpx.NetworkError, httpx.TimeoutException)),
        reraise=True,
    )
    async def query_analytics(
        self,
        site_url: str,
        page_url: str,
        start_date: date,
        end_date: date,
        row_limit: int = 25000,
    ) -> Dict[str, Any]:
        """
        Query daily clicks/impressions/ctr/position for a single page URL.

        ``site_url`` is the verified property (e.g. ``sc-domain:example.com``
        or ``https://example.com/``, exactly as returned by ``list_sites``);
        ``page_url`` is the full published article URL.
        """
        endpoint = f"{SEARCH_CONSOLE_BASE_URL}/sites/{quote(site_url, safe='')}/searchAnalytics/query"
        payload = {
            "startDate": start_date.isoformat(),
            "endDate": end_date.isoformat(),
            "dimensions": ["date"],
            "dimensionFilterGroups": [
                {
                    "filters": [
                        {"dimension": "page", "operator": "equals", "expression": page_url}
                    ]
                }
            ],
            "rowLimit": row_limit,
        }
        response = await self._request("POST", endpoint, json=payload)
        return response.json()

    async def _request(self, method: str, url: str, **kwargs) -> httpx.Response:
        try:
            response = await self._client.request(method, url, **kwargs)

            if response.status_code == 401:
                raise RextExternalServiceException(
                    message="Google Search Console authorization is invalid or expired.",
                    service_name="Search Console",
                )
            if response.status_code == 403:
                raise RextExternalServiceException(
                    message=(
                        "This Google account does not have access to the requested "
                        "Search Console property."
                    ),
                    service_name="Search Console",
                )
            if response.status_code == 404:
                raise RextExternalServiceException(
                    message="Search Console property not found.",
                    service_name="Search Console",
                )
            if response.status_code >= 400:
                raise RextExternalServiceException(
                    message=(
                        f"Search Console API returned unexpected status "
                        f"{response.status_code}: {response.text[:200]}"
                    ),
                    service_name="Search Console",
                )
            return response

        except (RextExternalServiceException, ExternalServiceTimeoutException):
            raise
        except httpx.TimeoutException:
            raise ExternalServiceTimeoutException(
                service_name="Search Console", timeout_seconds=int(_TIMEOUT)
            )
        except httpx.HTTPError as exc:
            logger.error(f"HTTP error calling Search Console API: {exc}")
            raise RextExternalServiceException(
                message="Unable to reach Google Search Console.",
                service_name="Search Console",
            )
