"""
Shopify App Bridge client.

Supports app-bridge connection setup and blog post publishing to the Shopify app
endpoint used by Rext.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import time
from pathlib import PurePosixPath
from typing import Any, Dict, Optional
from urllib.parse import urljoin

import httpx

from src.api.middleware.exceptions import (
    ExternalServiceTimeoutException,
    RextExternalServiceException,
    RextValidationException,
)
from src.utils.logger import logger

STORE_DOMAIN_RE = re.compile(r"^[a-z0-9][a-z0-9-]*[a-z0-9]$")


def normalize_store_url(value: str) -> str:
    """Normalize inputs like 'monitod' to 'https://monitod.myshopify.com'."""
    raw = (value or "").strip().rstrip("/")
    if not raw:
        raise RextValidationException(message="store_url must not be empty.")

    for scheme in ("https://", "http://"):
        if raw.startswith(scheme):
            raw = raw[len(scheme):]
            break

    raw = raw.lower()

    if raw.endswith(".myshopify.com"):
        handle = raw[: -len(".myshopify.com")]
    else:
        if "." in raw:
            raise RextValidationException(
                message=(
                    "Invalid Shopify store URL. Use a store handle (e.g. 'monitod') "
                    "or a myshopify domain (e.g. 'monitod.myshopify.com')."
                )
            )
        handle = raw

    if not STORE_DOMAIN_RE.match(handle):
        raise RextValidationException(
            message="Invalid Shopify store handle format in store_url."
        )

    return f"https://{handle}.myshopify.com"


def extract_store_handle(store_url: str) -> str:
    """Extract 'monitod' from normalized store URL."""
    normalized = normalize_store_url(store_url)
    host = normalized.replace("https://", "", 1)
    return host.replace(".myshopify.com", "", 1)


def build_admin_app_launch_url(
    store_handle: str,
    app_slug: str,
    entry_path: str = "/app/blogpost",
) -> str:
    """Build Shopify Admin app launch URL."""
    handle = (store_handle or "").strip().lower()
    slug = (app_slug or "").strip().strip("/")
    path = (entry_path or "/app/blogpost").strip()

    if not handle:
        raise RextValidationException(message="store handle is required.")
    if not STORE_DOMAIN_RE.match(handle):
        raise RextValidationException(message="Invalid store handle.")
    if not slug:
        raise RextValidationException(message="SHOPIFY_APP_SLUG is required.")

    if not path.startswith("/"):
        path = f"/{path}"

    return f"https://admin.shopify.com/store/{handle}/apps/{slug}{path}"


def _normalize_endpoint(endpoint: str) -> str:
    endpoint = (endpoint or "").strip()
    if not endpoint:
        return "/app/api/rext/publish"
    if not endpoint.startswith("/"):
        endpoint = f"/{endpoint}"
    return endpoint


def _to_int_article_id(raw: Any) -> Optional[int]:
    if raw is None:
        return None
    if isinstance(raw, int):
        return raw

    raw_str = str(raw)
    if raw_str.isdigit():
        return int(raw_str)

    # Supports gid://shopify/Article/123456789
    gid_match = re.search(r"(\d+)$", raw_str)
    if gid_match:
        return int(gid_match.group(1))

    return None


class ShopifyAppBridge:
    """HTTP client for Rext -> Shopify app bridge publishing."""

    def __init__(
        self,
        shared_secret: Optional[str],
        base_url: Optional[str] = None,
        publish_endpoint: str = "/app/api/rext/publish",
        timeout_seconds: float = 20.0,
        fallback_secret_seed: Optional[str] = None,
    ) -> None:
        self.shared_secret = (shared_secret or "").strip()
        self.base_url = (base_url or "").strip().rstrip("/")
        self.publish_endpoint = _normalize_endpoint(publish_endpoint)
        self.timeout_seconds = timeout_seconds
        self.fallback_secret_seed = (fallback_secret_seed or "").strip()

    def _derive_publish_url_from_launch_url(self, app_launch_url: str) -> Optional[str]:
        launch = (app_launch_url or "").strip()
        if not launch:
            return None

        if "/app/" not in launch:
            return urljoin(f"{launch.rstrip('/')}/", self.publish_endpoint.lstrip("/"))

        base, _ = launch.split("/app/", 1)
        endpoint = str(PurePosixPath(self.publish_endpoint))
        return f"{base}{endpoint}"

    def _resolve_publish_url(self, config_json: Optional[Dict[str, Any]]) -> str:
        cfg = config_json or {}
        override_url = (cfg.get("bridge_publish_url") or "").strip()
        if override_url:
            return override_url.rstrip("/")

        if self.base_url:
            return urljoin(f"{self.base_url}/", self.publish_endpoint.lstrip("/"))

        app_launch_url = (cfg.get("app_launch_url") or "").strip()
        derived = self._derive_publish_url_from_launch_url(app_launch_url)
        if derived:
            return derived

        raise RextValidationException(
            message=(
                "Shopify bridge publish URL is not configured. "
                "Connect the Shopify store again so app bridge metadata is saved."
            )
        )

    def _build_signature(self, timestamp: str, payload_bytes: bytes) -> str:
        secret = self.shared_secret
        if not secret and self.fallback_secret_seed:
            secret = hashlib.sha256(
                f"rext-shopify-bridge:{self.fallback_secret_seed}".encode("utf-8")
            ).hexdigest()

        if not secret:
            raise RextValidationException(
                message="Shopify bridge secret is unavailable for request signing."
            )

        signing_input = timestamp.encode("utf-8") + b"." + payload_bytes
        return hmac.new(
            secret.encode("utf-8"),
            signing_input,
            hashlib.sha256,
        ).hexdigest()

    async def publish_blog_post(
        self,
        *,
        store_url: str,
        title: str,
        body: str,
        published: bool,
        tags: Optional[list],
        handle: Optional[str],
        feature_image_url: Optional[str],
        content_id: str,
        workspace_id: str,
        config_json: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        normalized_store_url = normalize_store_url(store_url)
        store_handle = extract_store_handle(normalized_store_url)
        publish_url = self._resolve_publish_url(config_json)
        logger.info(f"Shopify App Bridge publishing to: {publish_url} (store: {normalized_store_url})")

        payload: Dict[str, Any] = {
            "storeUrl": normalized_store_url,
            "storeHandle": store_handle,
            "title": title,
            "body": body,
            "published": published,
            "tags": tags or [],
            "handle": handle,
            "featureImageUrl": feature_image_url,
            "contentId": content_id,
            "workspaceId": workspace_id,
        }

        payload_json = json.dumps(payload, separators=(",", ":"), ensure_ascii=True)
        payload_bytes = payload_json.encode("utf-8")

        timestamp = str(int(time.time()))
        signature = self._build_signature(timestamp, payload_bytes)

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-Rext-Timestamp": timestamp,
            "X-Rext-Signature": signature,
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(
                    publish_url,
                    content=payload_bytes,
                    headers=headers,
                )
        except httpx.TimeoutException as exc:
            logger.error(f"Shopify bridge publish timeout for {publish_url}: {exc}")
            raise ExternalServiceTimeoutException(
                service_name="Shopify App Bridge",
                timeout_seconds=int(self.timeout_seconds),
            )
        except httpx.HTTPError as exc:
            raise RextExternalServiceException(
                message=f"Network error calling Shopify App Bridge: {exc}",
                service_name="Shopify App Bridge",
                context={"publish_url": publish_url},
            )

        if response.status_code < 200 or response.status_code >= 300:
            body_snippet = response.text[:500]
            raise RextExternalServiceException(
                message=(
                    f"Shopify App Bridge publish failed with status {response.status_code}. "
                    f"Response: {body_snippet}"
                ),
                service_name="Shopify App Bridge",
                service_error=body_snippet,
                context={
                    "publish_url": publish_url,
                    "status_code": response.status_code,
                },
            )

        try:
            data = response.json()
        except ValueError as exc:
            raise RextExternalServiceException(
                message=f"Invalid JSON from Shopify App Bridge: {exc}",
                service_name="Shopify App Bridge",
                context={"publish_url": publish_url},
            )

        logger.info(f"Shopify App Bridge raw response: {data}")

        article = data.get("article") if isinstance(data, dict) else None
        article_obj = article if isinstance(article, dict) else (data if isinstance(data, dict) else {})

        article_id = _to_int_article_id(article_obj.get("id") or article_obj.get("articleId"))
        article_url = (
            article_obj.get("url")
            or article_obj.get("articleUrl")
            or article_obj.get("adminUrl")
        )

        if not article_id:
            raise RextExternalServiceException(
                message=(
                    f"Shopify App Bridge returned success but no article ID was found. "
                    f"The post may not have been published. Raw response: {str(data)[:500]}"
                ),
                service_name="Shopify App Bridge",
                service_error=str(data)[:500],
                context={"publish_url": publish_url, "raw_response": data},
            )

        return {
            "article_id": article_id,
            "article_url": article_url,
            "title": article_obj.get("title") or title,
            "published_at": article_obj.get("publishedAt") or article_obj.get("published_at"),
            "raw_response": data,
        }
