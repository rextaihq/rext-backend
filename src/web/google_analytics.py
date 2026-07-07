"""
Google Analytics 4 (GA4) Data API Client

Low-level httpx wrapper for the GA4 Data API (analyticsdata.googleapis.com).
Auth is via a bearer access token supplied by the caller — this client does
not refresh or persist tokens itself (see GoogleOAuthService for that).
"""

import logging
from datetime import date
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

GA4_DATA_API_BASE_URL = "https://analyticsdata.googleapis.com/v1beta"
_TIMEOUT = 20.0

GA4_METRICS = [
    "sessions",
    "activeUsers",
    "screenPageViews",
    "engagementRate",
    "averageSessionDuration",
    "bounceRate",
]


class GoogleAnalyticsClient:
    """GA4 Data API client, scoped to a single access token."""

    def __init__(self, access_token: str):
        self.access_token = access_token
        self._client = httpx.AsyncClient(
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            timeout=_TIMEOUT,
        )

    async def __aenter__(self) -> "GoogleAnalyticsClient":
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
    async def run_report(
        self,
        property_id: str,
        page_path: str,
        start_date: date,
        end_date: date,
    ) -> Dict[str, Any]:
        """
        Run a daily report scoped to a single page path.

        ``property_id`` must be in the form ``properties/123456789``.
        """
        endpoint = f"{GA4_DATA_API_BASE_URL}/{property_id}:runReport"
        payload = {
            "dateRanges": [
                {"startDate": start_date.isoformat(), "endDate": end_date.isoformat()}
            ],
            "dimensions": [{"name": "date"}],
            "metrics": [{"name": metric} for metric in GA4_METRICS],
            "dimensionFilter": {
                "filter": {
                    "fieldName": "pagePath",
                    "stringFilter": {"matchType": "EXACT", "value": page_path},
                }
            },
        }
        response = await self._request("POST", endpoint, json=payload)
        return response.json()

    async def validate_property(self, property_id: str) -> bool:
        """
        Confirm the connected account can query this GA4 property.

        Used when a user manually types in a GA4 property ID — listing
        properties programmatically requires the separate Analytics Admin
        API, which is not part of this integration's required Google Cloud
        setup (see docs).
        """
        endpoint = f"{GA4_DATA_API_BASE_URL}/{property_id}:runReport"
        payload = {
            "dateRanges": [{"startDate": "today", "endDate": "today"}],
            "metrics": [{"name": "sessions"}],
        }
        response = await self._request("POST", endpoint, json=payload, raise_on_403=False)
        return response.status_code == 200

    async def _request(
        self, method: str, url: str, raise_on_403: bool = True, **kwargs
    ) -> httpx.Response:
        try:
            response = await self._client.request(method, url, **kwargs)

            if response.status_code == 401:
                raise RextExternalServiceException(
                    message="Google Analytics authorization is invalid or expired.",
                    service_name="Google Analytics",
                )
            if response.status_code == 403:
                if raise_on_403:
                    raise RextExternalServiceException(
                        message=(
                            "This Google account does not have access to the requested "
                            "GA4 property."
                        ),
                        service_name="Google Analytics",
                    )
                return response
            if response.status_code == 404:
                raise RextExternalServiceException(
                    message="GA4 property not found.",
                    service_name="Google Analytics",
                )
            if response.status_code >= 400:
                raise RextExternalServiceException(
                    message=(
                        f"Google Analytics API returned unexpected status "
                        f"{response.status_code}: {response.text[:200]}"
                    ),
                    service_name="Google Analytics",
                )
            return response

        except (RextExternalServiceException, ExternalServiceTimeoutException):
            raise
        except httpx.TimeoutException:
            raise ExternalServiceTimeoutException(
                service_name="Google Analytics", timeout_seconds=int(_TIMEOUT)
            )
        except httpx.HTTPError as exc:
            logger.error(f"HTTP error calling GA4 Data API: {exc}")
            raise RextExternalServiceException(
                message="Unable to reach Google Analytics.",
                service_name="Google Analytics",
            )
