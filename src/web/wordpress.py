"""
WordPress Publishing Service

Handles publishing content to WordPress via REST API.
Move from src/services/wordpress_publisher.py to src/web/wordpress.py.
"""

import asyncio
import html
import json
import logging
import mimetypes
import os
import re
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import unquote, urlparse

import httpx
import markdown
from bs4 import BeautifulSoup
from pydantic import BaseModel, Field
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.api.middleware.exceptions import (
    ExternalServiceTimeoutException,
    RextExternalServiceException,
)
from src.api.schema.content_schema import ContentCreate
from src.flow.model.llm_manager import load_model
from src.utils.image_alt_text import build_image_alt_text
from src.utils.image_placeholder import strip_unresolved_placeholders
from src.utils.wordpress_status import normalize_wordpress_post_status

logger = logging.getLogger(__name__)

# Domains that only ever show up when an image URL was hallucinated by the
# model rather than being a real generated/uploaded asset.
_PLACEHOLDER_IMAGE_MARKERS = (
    "example.com",
    "example.org",
    "example.net",
    "placeholder.com",
    "via.placeholder",
    "dummyimage.com",
    "yourdomain.com",
    "your-domain.com",
    "domain.com",
    "image-url-here",
    "url-here",
    "your-image-url",
)

# Hard ceiling on how many existing categories get sent to the LLM for
# category matching — keeps the prompt (and cost) bounded on sites with an
# unusually large category list. Most sites have far fewer than this.
_MAX_CATEGORIES_FOR_LLM_MATCH = 200


class _CategoryMatch(BaseModel):
    """Structured output schema for LLM-based category matching."""

    category_id: Optional[int] = Field(
        default=None,
        description=(
            "The id of the single best-matching category from the provided "
            "list, or null if none of them are a genuine topical fit."
        ),
    )


def _is_placeholder_image_url(url: Optional[str]) -> bool:
    """True if `url` looks like a hallucinated/placeholder link rather than a real image asset."""
    if not isinstance(url, str) or not url.strip():
        return False
    lowered = url.strip().lower()
    if not lowered.startswith(("http://", "https://")):
        return True
    return any(marker in lowered for marker in _PLACEHOLDER_IMAGE_MARKERS)


def _extract_host(url: str) -> str:
    """Bare lowercase host for `url`, without scheme/port/www. Empty if not absolute."""
    if not url:
        return ""
    parsed = urlparse(url if "://" in url else f"//{url}")
    host = (parsed.netloc or "").lower().split(":")[0]
    if host.startswith("www."):
        host = host[4:]
    return host


def _apply_link_seo_rules(html: str, site_url: str) -> str:
    """SEO rule: internal links (same domain as the destination site) stay DoFollow;
    external links get rel="nofollow noopener" and open in a new tab.

    If the site's own domain can't be determined, links are left untouched rather
    than risking mislabeling a real internal link as external.
    """
    site_host = _extract_host(site_url)
    if not site_host:
        return html

    soup = BeautifulSoup(html, "html.parser")
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith(("#", "mailto:", "tel:")):
            continue
        href_host = _extract_host(href)
        if not href_host or href_host == site_host:
            continue  # relative link or same-site — DoFollow, leave as-is

        existing_rel = a.get("rel") or []
        if isinstance(existing_rel, str):
            existing_rel = existing_rel.split()
        a["rel"] = " ".join(sorted(set(existing_rel) | {"nofollow", "noopener"}))
        a["target"] = "_blank"

    return str(soup)


def _markdown_to_html(markdown_text: str, site_url: str) -> str:
    """Convert markdown to HTML and apply the internal/external link rel rules."""
    html = markdown.markdown(markdown_text or "", extensions=["extra"])
    return _apply_link_seo_rules(html, site_url)


def _build_json_ld_script(schema_markup: Optional[Dict[str, Any]]) -> str:
    """Build a <script type="application/ld+json"> block from stored schema markup.

    Returns an empty string if there's nothing valid to inject — never raises,
    so a missing/malformed schema never blocks publishing.
    """
    if not schema_markup or not isinstance(schema_markup, dict):
        return ""

    schema_data = schema_markup.get("schema_data")
    if not schema_data:
        return ""

    try:
        parsed = json.loads(schema_data) if isinstance(schema_data, str) else schema_data
        return f'<script type="application/ld+json">{json.dumps(parsed)}</script>'
    except (ValueError, TypeError):
        logger.warning("Invalid schema_markup JSON — skipping JSON-LD injection")
        return ""


class WordPressPublisher:
    """WordPress REST API client for publishing content."""

    def __init__(
        self,
        site_url: Optional[str] = None,
        api_endpoint: Optional[str] = None,
        username: Optional[str] = None,
        app_password: Optional[str] = None,
        api_key: Optional[str] = None,
        verify_ssl: bool = True,
    ):
        """
        Initialize WordPress publisher.

        Args:
            site_url: WordPress site URL (e.g., https://example.com)
            api_endpoint: Custom Rext-AI Plugin API endpoint (e.g. https://site.com/wp-json/rext-ai/v1/)
            username: WordPress username
            app_password: WordPress Application Password
            api_key: Rext-AI Plugin API Key (Bearer Token)
            verify_ssl: Whether to verify SSL certificates (set False for local dev)
        """
        self.site_url = site_url or os.getenv("WORDPRESS_SITE_URL", "")
        self.api_endpoint = api_endpoint or os.getenv("WORDPRESS_API_ENDPOINT", "")
        self.username = username or os.getenv("WORDPRESS_USERNAME", "")
        self.app_password = app_password or os.getenv("WORDPRESS_APP_PASSWORD", "")
        self.api_key = api_key or os.getenv("WORDPRESS_API_KEY", "")

        # SSL verification logic
        env = os.getenv("ENVIRONMENT", "development")
        if env == "production":
            self.verify_ssl = verify_ssl
        else:
            self.verify_ssl = False

        # Remove trailing slash from URLs
        self.site_url = self.site_url.rstrip("/")
        if self.api_endpoint:
            self.api_endpoint = self.api_endpoint.rstrip("/")

        # Remove spaces from application password
        self.app_password = (self.app_password or "").replace(" ", "")

        # Build client config
        # Do not set a client-wide Content-Type. httpx must generate the multipart
        # Content-Type (including its boundary) for WordPress media uploads.
        headers = {"Accept": "application/json"}
        auth = None

        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
            logger.info(f"WordPress publisher initialized with API key for site: {self.site_url}")
        elif self.username and self.app_password:
            auth = httpx.BasicAuth(self.username, self.app_password)
        else:
            logger.warning(
                "WordPress credentials not fully configured. "
                "Set WORDPRESS_SITE_URL, WORDPRESS_USERNAME, and WORDPRESS_APP_PASSWORD"
            )

        self.client = httpx.AsyncClient(
            verify=self.verify_ssl,
            headers=headers,
            auth=auth,
        )

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit, ensures client is closed."""
        await self.close()

    async def close(self):
        """Close the underlying HTTP client."""
        await self.client.aclose()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((httpx.NetworkError, httpx.TimeoutException)),
        reraise=True,
    )
    async def validate_plugin(self) -> bool:
        """
        Validate the Rext-AI WordPress plugin connection.

        Returns:
            True if valid, raises an exception if invalid.
        """
        endpoint = (
            self.api_endpoint if self.api_endpoint else f"{self.site_url}/wp-json/rext-ai/v1/"
        )

        try:
            response = await self.client.get(endpoint, timeout=15)

            if response.status_code == 200:
                return True
        except httpx.TimeoutException as e:
            error_msg = f"Timeout connecting to Rext-AI plugin at {endpoint}: {str(e)}"
            logger.error(error_msg)
            raise ExternalServiceTimeoutException(
                service_name="WordPress (Plugin)", timeout_seconds=15
            )

        except httpx.HTTPError as e:
            error_msg = f"Failed to connect to Rext-AI plugin at {endpoint}: {str(e)}"
            logger.error(error_msg)
            raise RextExternalServiceException(message=error_msg, service_name="WordPress")

        except Exception as e:
            error_msg = f"Unexpected error during WordPress plugin validation: {str(e)}"
            logger.error(error_msg)
            raise RextExternalServiceException(message=error_msg, service_name="WordPress")

    def _redact_headers(self, headers: Optional[Dict[str, str]]) -> Dict[str, str]:
        """Return a safe copy of headers without exposing credentials."""
        if not headers:
            return {}
        redacted = {}
        for key, value in headers.items():
            if key.lower() in {"authorization", "proxy-authorization"}:
                redacted[key] = "[REDACTED]"
            else:
                redacted[key] = value
        return redacted

    @staticmethod
    def _featured_media_id(post: Optional[Dict[str, Any]]) -> Optional[int]:
        """Read the media ID from WordPress core or the Rext plugin shape."""
        if not isinstance(post, dict):
            return None
        for key in ("featured_media", "featured_image"):
            value = post.get(key)
            if isinstance(value, int) and value > 0:
                return value
            if isinstance(value, dict):
                media_id = value.get("id")
                if isinstance(media_id, int) and media_id > 0:
                    return media_id
        return None

    @staticmethod
    def _taxonomy_ids(items: Any) -> set[int]:
        """Read taxonomy IDs from core IDs or plugin term dictionaries."""
        taxonomy_ids: set[int] = set()
        if not isinstance(items, list):
            return taxonomy_ids
        for item in items:
            if isinstance(item, int) and item > 0:
                taxonomy_ids.add(item)
            elif isinstance(item, dict):
                item_id = item.get("id") or item.get("term_id")
                if isinstance(item_id, int) and item_id > 0:
                    taxonomy_ids.add(item_id)
        return taxonomy_ids

    def _extract_image_urls_from_text(self, text: Optional[str]) -> List[str]:
        """Extract only image URLs embedded in markdown or HTML content."""
        if not text:
            return []
        urls: List[str] = []
        patterns = [
            r"!\[[^\]]*\]\((https?://[^)\s]+)\)",
            r'<img[^>]+src=["\'](https?://[^"\']+)["\']',
        ]
        for pattern in patterns:
            for match in re.finditer(pattern, text, flags=re.IGNORECASE):
                candidate = html.unescape(match.group(1) if match.lastindex else match.group(0))
                if candidate.startswith(("http://", "https://")) and candidate not in urls:
                    urls.append(candidate.rstrip(".,;:))"))
        return urls

    def _strip_first_embedded_image(self, content: str, image_url: str) -> str:
        """Remove the first inline occurrence of ``image_url`` from ``content``.

        When an image already embedded in the body is promoted to the WordPress
        featured image, the theme renders it a second time (as the post
        thumbnail) unless the inline copy is removed — otherwise the same photo
        shows up twice on the published page.
        """
        if not content or not image_url:
            return content
        # Markdown-to-HTML conversion escapes signed URL query separators, so the
        # raw URL may only be present in its HTML-escaped form.
        if image_url not in content and html.escape(image_url, quote=True) not in content:
            return content
        soup = BeautifulSoup(content, "html.parser")
        for img in soup.find_all("img"):
            src = html.unescape((img.get("src") or "").strip())
            if src != image_url:
                continue
            parent = img.parent
            if (
                parent is not None
                and parent.name == "p"
                and not parent.get_text(strip=True)
                and len(parent.find_all()) == 1
            ):
                parent.decompose()
            else:
                img.decompose()
            break
        return str(soup)

    def _is_existing_wordpress_media_url(self, image_url: str) -> bool:
        """Whether an image is already served by this WordPress media library."""
        parsed = urlparse(image_url)
        return (
            _extract_host(image_url) == _extract_host(self.site_url)
            and "/wp-content/uploads/" in parsed.path
        )

    def _extract_images_with_alt(self, content: Optional[str]) -> List[Tuple[str, str]]:
        """Return (src, alt) for every <img> with an http(s) src in the content.

        Parsed with BeautifulSoup so the alt text the user entered in the editor
        travels with the image URL to the WordPress media library.
        """
        if not content:
            return []
        results: List[Tuple[str, str]] = []
        seen: set = set()
        soup = BeautifulSoup(content, "html.parser")
        for img in soup.find_all("img"):
            src = html.unescape((img.get("src") or "").strip())
            if not src.startswith(("http://", "https://")) or src in seen:
                continue
            seen.add(src)
            results.append((src, (img.get("alt") or "").strip()))
        return results

    @staticmethod
    def _apply_alt_text_to_html(content: str, alt_by_src: Dict[str, str]) -> str:
        """Write resolved alt text onto the `<img>` tags in the post body.

        Yoast scores the alt attribute rendered on the page, so an image the
        user uploaded without alt text needs one in the HTML itself — setting
        it only on the media library entry would not count.
        """
        if not alt_by_src:
            return content
        soup = BeautifulSoup(content, "html.parser")
        changed = False
        for img in soup.find_all("img"):
            src = html.unescape((img.get("src") or "").strip())
            alt_text = alt_by_src.get(src)
            if alt_text and not (img.get("alt") or "").strip():
                img["alt"] = alt_text
                changed = True
        return str(soup) if changed else content

    async def _sync_embedded_images_to_wordpress(
        self,
        content: str,
        uploaded_media: Optional[Dict[str, Dict[str, Any]]] = None,
        title: Optional[str] = None,
        focus_keyphrase: Optional[str] = None,
    ) -> str:
        """Copy embedded post images to WordPress and rewrite their URLs.

        Only images still present as an <img> in the final post are synced. Each
        image's alt text is carried over to the WordPress media library, and an
        image embedded without any alt text gets one derived from the article so
        it isn't published with an empty alt attribute. Images already uploaded
        as the featured image are reused instead of being uploaded twice. A
        failure on one image is logged and skipped (its original URL is kept) so
        one bad image can't fail the whole publish.
        """
        media_by_source = dict(uploaded_media or {})
        resolved_alt_by_src: Dict[str, str] = {}

        for image_url, embedded_alt in self._extract_images_with_alt(content):
            alt_text = build_image_alt_text(
                user_alt=embedded_alt,
                title=title,
                focus_keyphrase=focus_keyphrase,
            )
            if alt_text and not embedded_alt:
                # Only images the user left without alt text get one written
                # back into the HTML; an explicit alt is never overwritten.
                resolved_alt_by_src[image_url] = alt_text

            if self._is_existing_wordpress_media_url(image_url):
                continue

            media_info = media_by_source.get(image_url)
            if media_info is None:
                try:
                    media_info = await self._upload_featured_image(image_url, alt_text=alt_text)
                except Exception:
                    logger.exception(
                        "[WordPress Publish] failed to sync embedded image url=%s; keeping original URL",
                        image_url,
                    )
                    continue
                media_by_source[image_url] = media_info
            elif alt_text and media_info.get("media_id"):
                # Reused (e.g. the featured image) but embedded with alt text —
                # make sure the media library entry reflects it.
                await self._set_media_alt_text(media_info["media_id"], alt_text)

            wordpress_url = media_info.get("url")
            if wordpress_url:
                content = content.replace(image_url, wordpress_url)
                content = content.replace(
                    html.escape(image_url, quote=True),
                    wordpress_url,
                )
                resolved_alt = resolved_alt_by_src.pop(image_url, None)
                if resolved_alt:
                    resolved_alt_by_src[wordpress_url] = resolved_alt

        return self._apply_alt_text_to_html(content, resolved_alt_by_src)

    @staticmethod
    def _entry_alt_text(entry: Any) -> str:
        """Read the alt text a payload entry carries alongside its image URL."""
        if not isinstance(entry, dict):
            return ""
        for key in ("alt_text", "alt", "caption"):
            value = entry.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return ""

    def _extract_feature_image(self, data: ContentCreate) -> Tuple[Optional[str], str]:
        """Extract the primary image URL *and its alt text* from payload data.

        Alt text travels with the URL so the featured image can be uploaded to
        the WordPress media library with its Alternative Text already set —
        the field Yoast reads when scoring images on the published page.

        Candidates that look hallucinated (e.g. example.com) are skipped rather
        than returned — a placeholder link must never become the post's
        featured image or a broken inline `<img>`.
        """
        images_data = getattr(data, "images_data", None)

        if isinstance(images_data, dict):
            for key in (
                "featured_image_url",
                "feature_image_url",
                "featured_image",
                "image_url",
                "source_url",
                "src",
                "url",
            ):
                value = images_data.get(key)
                if (
                    isinstance(value, str)
                    and value.strip()
                    and not _is_placeholder_image_url(value)
                ):
                    # A flat dict keeps its alt text as a sibling key.
                    return value.strip(), self._entry_alt_text(images_data)
            # Generation payloads may group candidates under images/items/data.
            for key in ("images", "items", "data"):
                value = images_data.get(key)
                if isinstance(value, list):
                    for item in value:
                        if (
                            isinstance(item, str)
                            and item.strip()
                            and not _is_placeholder_image_url(item)
                        ):
                            return item.strip(), ""
                        if isinstance(item, dict):
                            for url_key in ("url", "src", "image_url", "source_url"):
                                url = item.get(url_key)
                                if (
                                    isinstance(url, str)
                                    and url.strip()
                                    and not _is_placeholder_image_url(url)
                                ):
                                    return url.strip(), self._entry_alt_text(item)

        if isinstance(images_data, list):
            for item in images_data:
                if isinstance(item, str) and item.strip() and not _is_placeholder_image_url(item):
                    return item.strip(), ""
                if isinstance(item, dict):
                    for key in ("url", "src", "image_url"):
                        value = item.get(key)
                        if (
                            isinstance(value, str)
                            and value.strip()
                            and not _is_placeholder_image_url(value)
                        ):
                            return value.strip(), self._entry_alt_text(item)

        for text in (
            getattr(data, "body_markdown", None),
            getattr(data, "body_html", None),
            getattr(data, "introduction", None),
        ):
            for candidate in self._extract_image_urls_from_text(text):
                if not _is_placeholder_image_url(candidate):
                    # Alt for a body image is read from the rendered HTML by
                    # the caller, which has the converted content in hand.
                    return candidate, ""
        return None, ""

    def _extract_feature_image_url(self, data: ContentCreate) -> Optional[str]:
        """Primary image URL for the content payload (alt text discarded)."""
        image_url, _ = self._extract_feature_image(data)
        return image_url

    async def _request_with_retry(self, method: str, url: str, **kwargs) -> httpx.Response:
        """Helper to send HTTP requests with exponential backoff for 429 (Too Many Requests)."""
        import asyncio
        import random

        max_retries = 7
        base_delay = 3
        for attempt in range(max_retries + 1):
            response = await self.client.request(method, url, **kwargs)
            if response.status_code == 429 and attempt < max_retries:
                # Respect Retry-After header if present
                retry_after = response.headers.get("Retry-After")
                if retry_after and retry_after.isdigit():
                    delay = int(retry_after)
                else:
                    delay = base_delay * (2**attempt)
                # Add jitter to prevent thundering herd
                delay += random.uniform(0.5, 1.5)
                logger.warning(
                    f"[WordPress] HTTP 429 received for {url}. Retrying in {delay:.2f} seconds (Attempt {attempt + 1}/{max_retries})..."
                )
                await asyncio.sleep(delay)
                continue
            return response

    def _raise_for_status(self, response: httpx.Response) -> None:
        """Raise a useful HTTP exception even when the response lacks a bound request."""
        if response.status_code < 400:
            return
        request = getattr(response, "request", None)
        raise httpx.HTTPStatusError(
            f"HTTP {response.status_code} for {response.url}",
            request=request,
            response=response,
        )

    def _is_image_bytes(self, content: bytes, content_type: str) -> bool:
        """Validate common raster/SVG signatures instead of trusting a URL/header."""
        if not content:
            return False
        sample = content[:512].lstrip()
        signatures = (
            content.startswith(b"\xff\xd8\xff"),  # JPEG
            content.startswith(b"\x89PNG\r\n\x1a\n"),
            content.startswith((b"GIF87a", b"GIF89a")),
            content.startswith(b"BM"),
            content.startswith((b"II*\x00", b"MM\x00*")),  # TIFF
            content.startswith(b"RIFF") and content[8:12] == b"WEBP",
            sample.startswith(b"<svg") or (sample.startswith(b"<?xml") and b"<svg" in sample),
        )
        return content_type.startswith("image/") and any(signatures)

    def _upload_endpoint(self) -> str:
        if self.api_key and self.api_endpoint:
            return f"{self.api_endpoint}/media"
        return f"{self.site_url}/wp-json/wp/v2/media"

    def _local_storage_object_name(self, image_url: str) -> Optional[str]:
        """Return the object key when a URL points at Rext's own MinIO bucket."""
        from src.api.config import settings

        parsed = urlparse(image_url)
        endpoint = urlparse(
            settings.MINIO_ENDPOINT
            if "://" in settings.MINIO_ENDPOINT
            else f"//{settings.MINIO_ENDPOINT}"
        )
        storage_hosts = {
            "localhost",
            "127.0.0.1",
            "::1",
            "minio",
            endpoint.hostname,
        }
        if settings.MINIO_PUBLIC_URL:
            storage_hosts.add(urlparse(settings.MINIO_PUBLIC_URL).hostname)

        if parsed.hostname not in storage_hosts:
            return None

        path_parts = unquote(parsed.path).lstrip("/").split("/")
        if len(path_parts) < 2 or path_parts[0] != settings.MINIO_BUCKET:
            return None
        return "/".join(path_parts[1:])

    async def _download_image(self, image_url: str) -> httpx.Response:
        """Download an image without forwarding WordPress authentication."""
        object_name = self._local_storage_object_name(image_url)
        if object_name:
            from src.utils.storage import storage_service

            logger.info(
                "[WordPress Media Download] source=local_storage bucket=%s object=%s",
                storage_service.bucket_name,
                object_name,
            )
            content = await asyncio.to_thread(
                storage_service.download_file,
                object_name,
            )
            if content:
                content_type = mimetypes.guess_type(object_name)[0] or "application/octet-stream"
                logger.info(
                    "[WordPress Media Download] local_storage_success object=%s bytes=%s content_type=%s",
                    object_name,
                    len(content),
                    content_type,
                )
                return httpx.Response(
                    200,
                    content=content,
                    headers={"content-type": content_type},
                    request=httpx.Request("GET", image_url),
                )
            logger.warning(
                "[WordPress Media Download] local_storage_failed object=%s reason=%s; falling_back_to_http=true",
                object_name,
                storage_service.last_error or "object was not found",
            )

        async with httpx.AsyncClient(
            verify=self.verify_ssl,
            follow_redirects=True,
            headers={"Accept": "image/*"},
        ) as download_client:
            for attempt in range(1, 4):
                try:
                    logger.info(
                        "[WordPress Media Download] source=http attempt=%s/3 host=%s",
                        attempt,
                        urlparse(image_url).netloc,
                    )
                    return await download_client.get(image_url, timeout=30)
                except (httpx.NetworkError, httpx.TimeoutException) as exc:
                    logger.warning(
                        "[WordPress Media Download] http_attempt_failed attempt=%s/3 error_type=%s error=%r cause=%r",
                        attempt,
                        type(exc).__name__,
                        exc,
                        exc.__cause__,
                    )
                    if attempt == 3:
                        raise
                    await asyncio.sleep(0.5 * attempt)

        raise RuntimeError("Image download retry loop exited unexpectedly")

    async def _set_media_alt_text(self, media_id: int, alt_text: str) -> None:
        """Set alt text (and title) on an existing WordPress media item.

        WordPress ignores alt text sent with the binary upload, so it is applied
        with a follow-up update. Best-effort: a failure is logged, not raised.
        """
        if not media_id or not alt_text:
            return
        if self.api_key:
            # Plugin mode has no core /media/{id} update route; the alt text is
            # sent as a field on the upload request instead.
            return
        endpoint = f"{self._upload_endpoint()}/{media_id}"
        try:
            response = await self._request_with_retry(
                "POST",
                endpoint,
                json={"alt_text": alt_text, "title": alt_text},
                timeout=30,
            )
            if response.status_code not in (200, 201):
                logger.warning(
                    "[WordPress Media Alt] update failed media_id=%s status=%s body=%s",
                    media_id,
                    response.status_code,
                    response.text[:500],
                )
            else:
                logger.info(
                    "[WordPress Media Alt] set alt text media_id=%s alt=%r",
                    media_id,
                    alt_text,
                )
        except Exception:
            logger.exception("[WordPress Media Alt] error setting alt text media_id=%s", media_id)

    async def _upload_featured_image(
        self, image_url: str, alt_text: Optional[str] = None
    ) -> Dict[str, Any]:
        """Upload an image to the WordPress media library and return the media metadata.

        When ``alt_text`` is provided it is applied to the media item so it shows
        in the WordPress media library's Alternative Text field.
        """
        if not image_url:
            raise RextExternalServiceException(
                message="No featured image URL was provided",
                service_name="WordPress",
            )

        if image_url.strip().lower().startswith(("data:", "blob:")):
            reason = "Featured image is a base64/data/blob URL, not a downloadable image"
            logger.error(
                "[WordPress Media Upload] rejected image_url=%s reason=%s", image_url, reason
            )
            raise RextExternalServiceException(message=reason, service_name="WordPress")

        parsed_url = urlparse(image_url)
        if parsed_url.scheme not in {"http", "https"}:
            reason = f"Featured image is not an HTTP(S) URL: {image_url}"
            logger.error("[WordPress Media Upload] rejected reason=%s", reason)
            raise RextExternalServiceException(message=reason, service_name="WordPress")

        endpoint = self._upload_endpoint()
        filename = os.path.basename(parsed_url.path) or "image"

        logger.info("[WordPress Media Upload] called image_url=%s", image_url)
        logger.info("[WordPress Media Upload] download_request_url=%s", image_url)

        stage = "download"
        try:
            # Never forward WordPress credentials to the external image host.
            image_response = await self._download_image(image_url)
            logger.info("[WordPress Media Upload] download_status=%s", image_response.status_code)
            logger.info(
                "[WordPress Media Upload] download_headers=%s",
                self._redact_headers(dict(image_response.headers)),
            )
            logger.info(
                "[WordPress Media Upload] download_final_url=%s bytes=%s",
                image_response.url,
                len(image_response.content),
            )

            self._raise_for_status(image_response)

            content_type = image_response.headers.get("content-type", "").split(";", 1)[0].lower()
            if not self._is_image_bytes(image_response.content, content_type):
                preview = image_response.content[:200].decode("utf-8", errors="replace")
                reason = (
                    f"Downloaded resource is not a valid image "
                    f"(content_type={content_type!r}, bytes={len(image_response.content)}, "
                    f"body_preview={preview!r})"
                )
                logger.error(
                    "[WordPress Media Upload] validation_failed image_url=%s reason=%s",
                    image_url,
                    reason,
                )
                raise RextExternalServiceException(message=reason, service_name="WordPress")

            if "." not in filename:
                extension = mimetypes.guess_extension(content_type) or ""
                filename = f"image{extension}"

            files = {"file": (filename, image_response.content, content_type)}
            # Send alt text with the create request so it applies at upload time.
            # WordPress core reads these fields on POST /wp/v2/media; the plugin
            # endpoint gets them too (it must map alt_text -> _wp_attachment_image_alt).
            upload_data = {}
            if alt_text:
                upload_data["alt_text"] = alt_text
                upload_data["title"] = alt_text
            stage = "wordpress_upload"
            media_response = None
            for attempt in range(1, 4):
                request = self.client.build_request(
                    "POST",
                    endpoint,
                    files=files,
                    data=upload_data or None,
                    timeout=60,
                )
                logger.info(
                    "[WordPress Media Upload] attempt=%s/3 request_url=%s",
                    attempt,
                    request.url,
                )
                logger.info(
                    "[WordPress Media Upload] request_headers=%s",
                    self._redact_headers(dict(request.headers)),
                )
                logger.info(
                    "[WordPress Media Upload] request_file name=%s content_type=%s bytes=%s",
                    filename,
                    content_type,
                    len(image_response.content),
                )
                try:
                    media_response = await self.client.send(request)
                    if media_response.status_code == 429 and attempt < 3:
                        retry_after = media_response.headers.get("Retry-After")
                        delay = (
                            int(retry_after)
                            if retry_after and retry_after.isdigit()
                            else 2**attempt
                        )
                        logger.warning(
                            f"[WordPress] HTTP 429 received for media upload. Retrying in {delay} seconds (Attempt {attempt}/3)..."
                        )
                        await asyncio.sleep(delay)
                        continue
                    break
                except (httpx.NetworkError, httpx.TimeoutException) as exc:
                    logger.warning(
                        "[WordPress Media Upload] attempt_failed attempt=%s/3 error_type=%s error=%r cause=%r",
                        attempt,
                        type(exc).__name__,
                        exc,
                        exc.__cause__,
                    )
                    if attempt == 3:
                        raise
                    await asyncio.sleep(0.5 * attempt)

            if media_response is None:
                raise RuntimeError("WordPress media upload retry loop exited unexpectedly")
            logger.info("[WordPress Media Upload] upload_status=%s", media_response.status_code)
            logger.info("[WordPress Media Upload] upload_body=%s", media_response.text[:4000])

            if media_response.status_code != 201:
                reason = (
                    f"WordPress media API returned HTTP {media_response.status_code}; "
                    f"expected HTTP 201; body={media_response.text[:4000]}"
                )
                logger.error(
                    "[WordPress Media Upload] failed status=%s reason=%s",
                    media_response.status_code,
                    reason,
                )
                raise RextExternalServiceException(message=reason, service_name="WordPress")

            try:
                raw = media_response.json()
            except ValueError as exc:
                reason = f"WordPress media API returned invalid JSON: {media_response.text[:4000]}"
                logger.error("[WordPress Media Upload] failed reason=%s", reason)
                raise RextExternalServiceException(
                    message=reason, service_name="WordPress"
                ) from exc
            if not isinstance(raw, dict):
                raise RextExternalServiceException(
                    message=f"WordPress media API returned an unexpected JSON value: {raw!r}",
                    service_name="WordPress",
                )
            media_data = raw.get("data") if isinstance(raw.get("data"), dict) else raw
            media_id = media_data.get("id")
            media_url = (
                media_data.get("source_url") or media_data.get("link") or media_data.get("url")
            )

            if not isinstance(media_id, int) or media_id <= 0:
                logger.error("[WordPress Media Upload] response has no valid media id: %s", raw)
                raise RextExternalServiceException(
                    message="WordPress media upload response did not include a valid media id",
                    service_name="WordPress",
                )

            logger.info(
                "[WordPress Media Upload] succeeded: media_id=%s url=%s",
                media_id,
                media_url,
            )
            if alt_text:
                await self._set_media_alt_text(media_id, alt_text)
                if self.api_key and not (media_data.get("alt_text") or "").strip():
                    # Plugin mode has no /media/{id} update route, so the
                    # multipart alt_text field is the only channel — surface it
                    # when a plugin build silently drops it, rather than
                    # publishing images with an empty alt attribute unnoticed.
                    logger.warning(
                        "[WordPress Media Upload] media_id=%s was uploaded with "
                        "alt=%r but the plugin response reports no alt_text; the "
                        "WordPress plugin may not map alt_text to "
                        "_wp_attachment_image_alt",
                        media_id,
                        alt_text,
                    )
            return {"media_id": media_id, "url": media_url}

        except httpx.TimeoutException as e:
            reason = (
                f"Featured image {stage} timed out for "
                f"{parsed_url.scheme}://{parsed_url.netloc}{parsed_url.path}; "
                f"error={type(e).__name__}({e!r}); cause={e.__cause__!r}"
            )
            logger.exception("[WordPress Media Upload] failed reason=%s", reason)
            raise ExternalServiceTimeoutException(
                service_name="WordPress Media", timeout_seconds=60
            ) from e
        except httpx.NetworkError as e:
            reason = (
                f"Featured image {stage} network connection failed for "
                f"{parsed_url.scheme}://{parsed_url.netloc}{parsed_url.path} "
                f"after 3 attempts; error={type(e).__name__}({e!r}); "
                f"cause={e.__cause__!r}"
            )
            logger.exception(
                "[WordPress Media Upload] failed image_url=%s reason=%s",
                image_url,
                reason,
            )
            raise RextExternalServiceException(
                message=reason,
                service_name="WordPress",
            ) from e
        except httpx.HTTPStatusError as e:
            body = e.response.text[:4000] if e.response is not None else ""
            reason = f"Image request failed: {e}; body={body}"
            logger.exception(
                "[WordPress Media Upload] failed image_url=%s reason=%s", image_url, reason
            )
            raise RextExternalServiceException(message=reason, service_name="WordPress") from e
        except RextExternalServiceException:
            raise
        except Exception as e:
            reason = (
                f"Unexpected featured image {stage} error: "
                f"{type(e).__name__}({e!r}); cause={e.__cause__!r}"
            )
            logger.exception(
                "[WordPress Media Upload] failed image_url=%s reason=%s", image_url, reason
            )
            raise RextExternalServiceException(message=reason, service_name="WordPress") from e

    async def _confirm_featured_media_cleared(
        self,
        post: Dict[str, Any],
        status: str,
    ) -> bool:
        """Verify a removed featured image really is gone, correcting it once.

        Publishing an article whose image the user deleted can update a post
        that still carries the old thumbnail. We send featured_media=0, then
        confirm it took; if the thumbnail survived, one explicit update is
        attempted before giving up and logging.

        Returns whether the post ended up with no thumbnail. Never raises: the
        post itself published correctly, and some plugin builds don't report
        featured_media at all.
        """
        post_id = post.get("id") or post.get("post_id")
        if not isinstance(post_id, int) or post_id <= 0:
            return True

        # WordPress core echoes featured_media on create. When it explicitly
        # reports no thumbnail, that answers the question — skip the extra
        # round trip. Only an absent field (some plugin builds omit it) leaves
        # enough doubt to be worth a verification fetch.
        if any(key in post for key in ("featured_media", "featured_image")):
            if not self._featured_media_id(post):
                return True

        verified_post = await self._fetch_post_for_featured_media(post_id, status)
        stale_media_id = self._featured_media_id(verified_post)
        if not stale_media_id:
            return True

        logger.warning(
            "[WordPress Publish] post_id=%s kept a previous featured image "
            "(media_id=%s) after featured_media=0; retrying explicitly",
            post_id,
            stale_media_id,
        )
        try:
            await self.update_post(post_id, featured_media=0)
        except Exception:
            logger.exception(
                "[WordPress Publish] corrective featured image removal failed post_id=%s",
                post_id,
            )
            return False

        verified_post = await self._fetch_post_for_featured_media(post_id, status)
        stale_media_id = self._featured_media_id(verified_post)
        if stale_media_id:
            logger.error(
                "[WordPress Publish] post_id=%s still has featured image media_id=%s "
                "after an explicit removal; the site may need to be checked manually",
                post_id,
                stale_media_id,
            )
            return False

        logger.info("[WordPress Publish] post_id=%s previous featured image removed", post_id)
        return True

    async def _fetch_post_for_featured_media(
        self,
        post_id: int,
        status: str,
    ) -> Optional[Dict[str, Any]]:
        """Fetch the created post when a custom create response omits fields."""
        if self.api_key and self.api_endpoint:
            verification_endpoint = f"{self.api_endpoint}/posts/{post_id}"
        else:
            verification_endpoint = f"{self.site_url}/wp-json/wp/v2/posts/{post_id}"

        logger.info("[WordPress Verify] request_url=%s", verification_endpoint)
        logger.info(
            "[WordPress Verify] request_headers=%s",
            self._redact_headers(dict(self.client.headers)),
        )
        plugin_post = None
        try:
            response = await self.client.get(verification_endpoint, timeout=30)
            logger.info("[WordPress Verify] response_status=%s", response.status_code)
            logger.info("[WordPress Verify] response_body=%s", response.text[:4000])
            if response.status_code == 200:
                raw = response.json()
                if isinstance(raw, dict):
                    plugin_post = raw.get("data") if isinstance(raw.get("data"), dict) else raw
                    plugin_media_id = self._featured_media_id(plugin_post)
                    if plugin_media_id:
                        plugin_post = {
                            **plugin_post,
                            "featured_media": plugin_media_id,
                        }
                    if not self.api_endpoint or plugin_media_id is not None:
                        return plugin_post
        except Exception as exc:
            logger.warning(
                "[WordPress Verify] custom/authenticated lookup failed post_id=%s reason=%s",
                post_id,
                exc,
            )

        # A published post is readable from the core API even when the custom
        # plugin has no GET /posts/{id} route. Do not forward plugin credentials.
        if status == "publish" and self.api_endpoint:
            core_endpoint = f"{self.site_url}/wp-json/wp/v2/posts/{post_id}"
            logger.info("[WordPress Verify] fallback_request_url=%s", core_endpoint)
            try:
                async with httpx.AsyncClient(
                    verify=self.verify_ssl,
                    headers={"Accept": "application/json"},
                ) as public_client:
                    response = await public_client.get(core_endpoint, timeout=30)
                logger.info("[WordPress Verify] fallback_response_status=%s", response.status_code)
                logger.info("[WordPress Verify] fallback_response_body=%s", response.text[:4000])
                if response.status_code == 200:
                    raw = response.json()
                    if isinstance(raw, dict):
                        return {**(plugin_post or {}), **raw}
            except Exception as exc:
                logger.warning(
                    "[WordPress Verify] core lookup failed post_id=%s reason=%s",
                    post_id,
                    exc,
                )

        return plugin_post

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((httpx.NetworkError, httpx.TimeoutException)),
        reraise=True,
    )
    async def publish_post(
        self,
        data: ContentCreate,
        status: str = "publish",
        excerpt: Optional[str] = None,
        tags: Optional[List[str]] = None,
        categories: Optional[List[int]] = None,
        meta: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        status = normalize_wordpress_post_status(status)
        logger.info(
            "[WordPress Status] selected_status=%s request_status=%s",
            status,
            status,
        )

        if self.api_key and self.api_endpoint:
            endpoint = f"{self.api_endpoint}/posts"
        else:
            endpoint = f"{self.site_url}/wp-json/wp/v2/posts"

        title = data.title

        # Markdown is the source of truth: convert fresh at publish time so the
        # DoFollow (internal) / NoFollow (external) link rule always applies,
        # regardless of whatever (possibly stale) body_html was stored.
        #
        # Manual-upload image placeholders (rext-placeholder:<id>) are not real
        # URLs — they exist only so the editor can render an upload slot. If the
        # user never resolved or dismissed one, it must be stripped here rather
        # than published as a broken <img> on the live site.
        intro_text = strip_unresolved_placeholders(data.introduction)
        body_markdown_text = strip_unresolved_placeholders(data.body_markdown)
        body_html_text = strip_unresolved_placeholders(data.body_html)

        markdown_parts = []
        if intro_text:
            markdown_parts.append(intro_text)
        if body_markdown_text:
            markdown_parts.append(body_markdown_text)

        if markdown_parts:
            content = _markdown_to_html("\n\n".join(markdown_parts), self.site_url)
        else:
            # No markdown available at all — fall back to whatever HTML/intro we have.
            content_parts = []
            if intro_text:
                content_parts.append(intro_text)
            if body_html_text:
                content_parts.append(body_html_text)
            content = "\n\n".join(content_parts)

        json_ld = _build_json_ld_script(data.schema_markup)
        if json_ld:
            content = f"{content}\n{json_ld}"

        if not content:
            raise ValueError("Content body (HTML or Markdown) is required for publishing")

        meta_title = data.seo_data.meta_title if data.seo_data else None
        meta_description = data.seo_data.meta_description if data.seo_data else None
        focus_keyword = data.seo_data.focus_keyphrase if data.seo_data else None

        if not excerpt and meta_description:
            excerpt = meta_description
        if not focus_keyword and data.seo_data:
            focus_keyword = data.seo_data.focus_keyphrase

        if not tags and data.tags:
            tags = data.tags

        post_data = {
            "title": title,
            "content": content,
            "status": status,
        }

        uploaded_media: Dict[str, Dict[str, Any]] = {}
        image_url, images_data_alt = self._extract_feature_image(data)
        media_info = None
        if image_url:
            logger.info("[WordPress Publish] detected featured image url=%s", image_url)
            # Resolve alt text while the image is still in the body — the alt the
            # user typed in the editor lives on the <img>, and the inline copy is
            # stripped below before the embedded-image sync could ever see it.
            body_alt = dict(self._extract_images_with_alt(content)).get(image_url, "")
            featured_alt = build_image_alt_text(
                user_alt=images_data_alt or body_alt,
                title=title,
                focus_keyphrase=focus_keyword,
            )
            logger.info("[WordPress Publish] featured image alt=%r", featured_alt)
            try:
                media_info = await self._upload_featured_image(image_url, alt_text=featured_alt)
            except Exception:
                # A missing/broken featured image (e.g. deleted from storage)
                # must not abort the whole publish - post without one instead.
                logger.exception(
                    "[WordPress Publish] failed to upload featured image url=%s; publishing without it",
                    image_url,
                )
                media_info = None

        if media_info:
            uploaded_media[image_url] = media_info
            post_data["featured_media"] = media_info["media_id"]
            # The Rext-AI plugin names the thumbnail input `featured_image`;
            # WordPress core names it `featured_media`. Send both in plugin mode.
            if self.api_key and self.api_endpoint:
                post_data["featured_image"] = media_info["media_id"]
            # The theme renders featured_media automatically — drop the inline
            # copy so the same photo doesn't also appear inside the article body.
            content = self._strip_first_embedded_image(content, image_url)
            post_data["content"] = content
        else:
            # The article currently has no usable image. Say so explicitly:
            # publishing this post may update one that already carries a
            # thumbnail from an earlier publish, and omitting the field would
            # silently leave that stale image attached. WordPress reads
            # featured_media=0 as "no thumbnail".
            logger.info(
                "[WordPress Publish] no featured image in the current payload; "
                "clearing any thumbnail from a previous publish"
            )
            post_data["featured_media"] = 0
            if self.api_key and self.api_endpoint:
                post_data["featured_image"] = 0

        content = await self._sync_embedded_images_to_wordpress(
            content,
            uploaded_media=uploaded_media,
            title=title,
            focus_keyphrase=focus_keyword,
        )
        post_data["content"] = content

        if excerpt:
            post_data["excerpt"] = excerpt

        if tags:
            tag_ids = await self._get_or_create_tags(tags)
            if tag_ids:
                post_data["tags"] = tag_ids
                if self.api_key and self.api_endpoint:
                    post_data["tags_input"] = tag_ids

        if categories:
            post_data["categories"] = categories
            if self.api_key and self.api_endpoint:
                post_data["post_category"] = categories
            logger.info(
                "[WordPress Category] using caller-provided category_ids=%s",
                categories,
            )
        else:
            logger.info(
                "[WordPress Category] no explicit category IDs provided; matching against existing categories"
            )
            all_existing_categories = await self._fetch_all_categories()

            ai_category = getattr(data, "category", None)

            auto_category_ids = await self._select_relevant_category_via_llm(
                title=title,
                focus_keyword=focus_keyword,
                excerpt=excerpt,
                existing_categories=all_existing_categories,
            )
            if auto_category_ids:
                post_data["categories"] = auto_category_ids
                logger.info(
                    "[WordPress Category] publishing with category_ids=%s", auto_category_ids
                )
            elif ai_category:
                # No existing category scored well enough; fall back to creating
                # (or reusing) a category named after the AI-suggested topic
                # rather than leaving the post uncategorized.
                fallback_name = str(ai_category).split(",")[0].strip()
                if fallback_name:
                    try:
                        category_id = await self._get_or_create_category(fallback_name)
                        post_data["categories"] = [category_id]
                        logger.info(
                            "[WordPress Category] no relevant existing category found; "
                            "created/reused name=%s category_id=%s",
                            fallback_name,
                            category_id,
                        )
                    except Exception as exc:
                        logger.warning(
                            "[WordPress Category] fallback category creation failed for name=%s: %s",
                            fallback_name,
                            exc,
                        )
                else:
                    logger.info("[WordPress Category] no relevant existing category found")
            else:
                logger.info("[WordPress Category] no relevant existing category found")

        # Send SEO data in the format expected by the Rext-AI plugin
        seo_data = {}

        if meta_title:
            seo_data["meta_title"] = meta_title

        if meta_description:
            seo_data["meta_description"] = meta_description

        if focus_keyword:
            seo_data["focus_keyword"] = focus_keyword

        # Keep support for any additional SEO fields passed by caller
        if meta:
            seo_data.update(meta)

        if seo_data:
            post_data["seo"] = seo_data

        logger.info("[WordPress Publish] payload=%s", post_data)

        # True unless we asked WordPress to drop a thumbnail and it kept one.
        featured_media_cleared = True

        try:
            logger.info("[WordPress Publish] publishing title=%s to endpoint=%s", title, endpoint)
            logger.info(
                "[WordPress Publish] request_headers=%s",
                self._redact_headers(dict(self.client.headers)),
            )

            response = await self._request_with_retry(
                "POST",
                endpoint,
                json=post_data,
                timeout=30,
            )

            logger.info("[WordPress Publish] post_response_status=%s", response.status_code)
            logger.info("[WordPress Publish] post_response_body=%s", response.text[:4000])
            self._raise_for_status(response)

            raw = response.json()
            if not isinstance(raw, dict):
                raise RextExternalServiceException(
                    message=f"WordPress Posts API returned an unexpected JSON value: {raw!r}",
                    service_name="WordPress",
                )
            post = raw.get("data") if isinstance(raw.get("data"), dict) else raw
            returned_status = post.get("status")
            if returned_status != status:
                post_id = post.get("id") or post.get("post_id")
                verified_post = None
                if isinstance(post_id, int) and post_id > 0:
                    verified_post = await self._fetch_post_for_featured_media(
                        post_id,
                        status,
                    )
                verified_status = (
                    verified_post.get("status") if isinstance(verified_post, dict) else None
                )
                logger.info(
                    "[WordPress Status] verify post_id=%s expected=%s create_response=%s fetched_post=%s",
                    post_id,
                    status,
                    returned_status,
                    verified_status,
                )
                if verified_status != status:
                    reason = (
                        "WordPress did not confirm the requested post status "
                        f"(post_id={post_id}, sent={status}, "
                        f"create_response={returned_status}, fetched_post={verified_status})"
                    )
                    logger.error(
                        "[WordPress Status] verification_failed reason=%s",
                        reason,
                    )
                    raise RextExternalServiceException(
                        message=reason,
                        service_name="WordPress",
                    )
                post = {**post, **verified_post}

            logger.info(
                "[WordPress Publish] post_response_featured_media=%s", post.get("featured_media")
            )
            if post_data.get("featured_media"):
                returned_media_id = self._featured_media_id(post)
                if returned_media_id != post_data["featured_media"]:
                    post_id = post.get("id") or post.get("post_id")
                    verified_post = None
                    if isinstance(post_id, int) and post_id > 0:
                        verified_post = await self._fetch_post_for_featured_media(post_id, status)
                    verified_media_id = self._featured_media_id(verified_post)
                    logger.info(
                        "[WordPress Verify] post_id=%s expected_featured_media=%s actual_featured_media=%s",
                        post_id,
                        post_data["featured_media"],
                        verified_media_id,
                    )
                    if verified_media_id != post_data["featured_media"]:
                        reason = (
                            "WordPress did not confirm the requested featured image "
                            f"(post_id={post_id}, sent={post_data['featured_media']}, "
                            f"create_response={returned_media_id}, fetched_post={verified_media_id})"
                        )
                        logger.error("[WordPress Publish] verification_failed reason=%s", reason)
                        raise RextExternalServiceException(message=reason, service_name="WordPress")
                    post = {**post, **verified_post}
            elif post_data.get("featured_media") == 0:
                # We asked for no thumbnail. If the post still carries one from
                # an earlier publish, correct it once. Unlike the set case this
                # never raises: some plugin builds simply don't echo or accept
                # the field, and a post that published fine shouldn't be
                # reported as failed over a thumbnail we can only warn about.
                featured_media_cleared = await self._confirm_featured_media_cleared(post, status)

            if "categories" in post_data:
                expected_category_ids = set(post_data["categories"])
                returned_categories = post.get("categories")
                returned_category_ids = self._taxonomy_ids(returned_categories)
                if not expected_category_ids.issubset(returned_category_ids):
                    post_id = post.get("id") or post.get("post_id")
                    verified_post = None
                    if isinstance(post_id, int) and post_id > 0:
                        verified_post = await self._fetch_post_for_featured_media(post_id, status)
                    fetched_categories = (
                        verified_post.get("categories") if isinstance(verified_post, dict) else []
                    )
                    verified_category_ids = self._taxonomy_ids(fetched_categories)
                    logger.info(
                        "[WordPress Category] verify post_id=%s expected=%s actual=%s",
                        post_id,
                        sorted(expected_category_ids),
                        sorted(category_id for category_id in verified_category_ids if category_id),
                    )
                    if not expected_category_ids.issubset(verified_category_ids):
                        reason = (
                            "WordPress did not confirm the requested categories "
                            f"(post_id={post_id}, sent={sorted(expected_category_ids)}, "
                            f"fetched_post={sorted(category_id for category_id in verified_category_ids if category_id)})"
                        )
                        logger.error("[WordPress Category] verification_failed reason=%s", reason)
                        raise RextExternalServiceException(
                            message=reason,
                            service_name="WordPress",
                        )
                    post = {**post, **verified_post}

            return {
                "success": True,
                "post_id": post.get("id") or post.get("post_id"),
                "link": post.get("url") or post.get("link"),
                "status": post.get("status"),
                "title": post.get("title"),
                "featured_media": post.get("featured_media"),
                "featured_media_cleared": featured_media_cleared,
            }

        except httpx.TimeoutException as e:
            error_msg = f"Timeout while publishing post to WordPress: {str(e)}"
            logger.error(error_msg)
            raise ExternalServiceTimeoutException(service_name="WordPress", timeout_seconds=30)

    async def _get_or_create_tags(self, tag_names: List[str]) -> List[int]:
        """Get tag IDs for tag names, creating them if they don't exist.

        Handles both the standard WP REST API (plain JSON array) and the Rext
        plugin format that wraps the list in ``{"data": [...]}``.
        """
        tag_ids = []
        if self.api_key and self.api_endpoint:
            endpoint = f"{self.api_endpoint}/tags"
        else:
            endpoint = f"{self.site_url}/wp-json/wp/v2/tags"

        for tag_name in tag_names:
            name = (tag_name or "").strip()
            if not name:
                continue
            try:
                logger.info("[WordPress Tag] lookup name=%s request_url=%s", name, endpoint)
                response = await self._request_with_retry(
                    "GET",
                    endpoint,
                    params={"search": name, "per_page": 100},
                    timeout=10,
                )
                logger.info("[WordPress Tag] lookup_status=%s", response.status_code)
                logger.info("[WordPress Tag] lookup_body=%s", response.text[:2000])

                if response.status_code == 200:
                    raw = response.json()
                    # Unwrap plugin envelope {"data": [...]} or use plain list
                    if isinstance(raw, dict) and isinstance(raw.get("data"), list):
                        candidates = raw["data"]
                    elif isinstance(raw, list):
                        candidates = raw
                    else:
                        candidates = []

                    # Exact case-insensitive name match
                    matched_id = None
                    for candidate in candidates:
                        if not isinstance(candidate, dict):
                            continue
                        candidate_name = str(candidate.get("name") or "").strip()
                        cid = candidate.get("id") or candidate.get("term_id")
                        if candidate_name.casefold() == name.casefold() and isinstance(cid, int):
                            matched_id = cid
                            break

                    if matched_id:
                        logger.info("[WordPress Tag] found name=%s tag_id=%s", name, matched_id)
                        tag_ids.append(matched_id)
                        continue

                    # Not found — create it
                    logger.info(
                        "[WordPress Tag] not_found name=%s; creating at request_url=%s",
                        name,
                        endpoint,
                    )
                    create_response = await self._request_with_retry(
                        "POST",
                        endpoint,
                        json={"name": name},
                        timeout=10,
                    )
                    logger.info("[WordPress Tag] create_status=%s", create_response.status_code)
                    logger.info("[WordPress Tag] create_body=%s", create_response.text[:2000])
                    create_raw = create_response.json()

                    # Handle WP's "term_exists" 400 — reuse existing term
                    if create_response.status_code == 400 and isinstance(create_raw, dict):
                        existing_id = (
                            create_raw.get("data", {}).get("term_id")
                            if isinstance(create_raw.get("data"), dict)
                            else None
                        )
                        if isinstance(existing_id, int) and existing_id > 0:
                            logger.info(
                                "[WordPress Tag] concurrent_create_reused name=%s tag_id=%s",
                                name,
                                existing_id,
                            )
                            tag_ids.append(existing_id)
                            continue

                    if create_response.status_code in (200, 201):
                        tag_obj = (
                            create_raw.get("data")
                            if isinstance(create_raw, dict)
                            and isinstance(create_raw.get("data"), dict)
                            else create_raw
                        )
                        tag_id = (
                            tag_obj.get("id") or tag_obj.get("term_id")
                            if isinstance(tag_obj, dict)
                            else None
                        )
                        if isinstance(tag_id, int) and tag_id > 0:
                            logger.info("[WordPress Tag] created name=%s tag_id=%s", name, tag_id)
                            tag_ids.append(tag_id)
                        else:
                            logger.warning(
                                "[WordPress Tag] create response missing valid id for name=%s body=%s",
                                name,
                                create_raw,
                            )
                    else:
                        logger.warning(
                            "[WordPress Tag] create failed name=%s status=%s body=%s",
                            name,
                            create_response.status_code,
                            create_response.text[:500],
                        )

            except Exception as e:
                logger.warning("[WordPress Tag] could not process tag '%s': %s", name, e)
                continue

        return tag_ids

    async def _fetch_all_categories(self) -> List[Dict[str, Any]]:
        """Fetch all existing WordPress categories, handling pagination."""
        if hasattr(self, "_cached_categories") and self._cached_categories is not None:
            return self._cached_categories

        logger.info("[WordPress Category] fetching all categories")
        all_categories = []
        page = 1
        per_page = 100
        # Hard ceiling so a plugin endpoint that ignores `page` (and therefore
        # never returns an empty page or a matching X-WP-TotalPages header)
        # can't spin this into an unbounded loop that hammers the site with
        # requests until it starts 429-ing.
        max_pages = 50
        seen_ids: set = set()

        if self.api_key and self.api_endpoint:
            endpoint = f"{self.api_endpoint}/categories"
        else:
            endpoint = f"{self.site_url}/wp-json/wp/v2/categories"

        while page <= max_pages:
            try:
                response = await self._request_with_retry(
                    "GET", endpoint, params={"per_page": per_page, "page": page}, timeout=30
                )
                if response.status_code == 400 and page > 1:
                    break
                response.raise_for_status()

                raw = response.json()
                if isinstance(raw, dict) and isinstance(raw.get("data"), list):
                    page_categories = raw["data"]
                elif isinstance(raw, list):
                    page_categories = raw
                else:
                    break

                if not page_categories:
                    break

                page_ids = {
                    cat.get("id") or cat.get("term_id")
                    for cat in page_categories
                    if isinstance(cat, dict)
                }
                # A page whose ids we've already collected means the endpoint
                # isn't honoring pagination (e.g. ignores the `page` param) and
                # is just replaying the same results — stop instead of looping.
                if page_ids and page_ids.issubset(seen_ids):
                    logger.warning(
                        "[WordPress Category] page %d repeated previously-seen categories; "
                        "endpoint likely does not support pagination, stopping",
                        page,
                    )
                    break

                for cat in page_categories:
                    if isinstance(cat, dict):
                        cat_id = cat.get("id") or cat.get("term_id")
                        if isinstance(cat_id, int) and cat_id not in seen_ids:
                            seen_ids.add(cat_id)
                            all_categories.append(
                                {
                                    "id": cat_id,
                                    "name": cat.get("name", ""),
                                    "slug": cat.get("slug", ""),
                                }
                            )

                # Fewer results than requested means this was the last page.
                if len(page_categories) < per_page:
                    break

                total_pages = response.headers.get("X-WP-TotalPages")
                if total_pages and str(page) == total_pages:
                    break

                page += 1
            except Exception as e:
                logger.warning(f"[WordPress Category] error fetching categories page {page}: {e}")
                break

        logger.info("[WordPress Category] retrieved %d categories", len(all_categories))
        self._cached_categories = all_categories
        return all_categories

    async def _select_relevant_category_via_llm(
        self,
        title: Optional[str],
        focus_keyword: Optional[str],
        excerpt: Optional[str],
        existing_categories: List[Dict[str, Any]],
    ) -> List[int]:
        """Ask a low-cost LLM to pick the single best-fitting existing category.

        Only clean, minimal signal is sent — title, focus keyword, a short
        excerpt, and the category id/name list — never the full article body,
        to keep the call small, fast, and cheap. The model may only return one
        of the ids it was given (validated below); anything else, or any
        failure, is treated as no match so the caller falls back to its
        existing "create from AI-suggested name" behavior.
        """
        if not existing_categories or not (title or focus_keyword or excerpt):
            return []

        catalog = existing_categories[:_MAX_CATEGORIES_FOR_LLM_MATCH]
        category_lines = "\n".join(f"{c['id']}: {c['name']}" for c in catalog if c.get("name"))
        if not category_lines:
            return []

        prompt = (
            "You are choosing the best-fitting WordPress category for an article.\n\n"
            f"Article title: {title or '(none)'}\n"
            f"Focus keyword: {focus_keyword or '(none)'}\n"
            f"Excerpt: {(excerpt or '(none)')[:500]}\n\n"
            "Existing categories (id: name):\n"
            f"{category_lines}\n\n"
            "Pick the id of the single category that is a genuine topical fit "
            "for this article. If none of them genuinely fit, return null — "
            "do not force a weak match."
        )

        try:
            model = load_model(max_tokens=200).with_structured_output(_CategoryMatch)
            result = await model.ainvoke(prompt)
            category_id = getattr(result, "category_id", None)
        except Exception:
            logger.exception("[WordPress Category] LLM category selection failed; falling back")
            return []

        valid_ids = {c["id"] for c in catalog}
        if isinstance(category_id, int) and category_id in valid_ids:
            logger.info("[WordPress Category] LLM selected category_id=%s", category_id)
            return [category_id]

        logger.info("[WordPress Category] LLM found no matching category")
        return []

    async def _get_or_create_category(self, category_name: str) -> int:
        """Resolve a WordPress category by exact name, creating it when absent."""
        name = (category_name or "").strip()
        if not name:
            raise ValueError("Category name cannot be empty")

        if self.api_key and self.api_endpoint:
            endpoint = f"{self.api_endpoint}/categories"
        else:
            endpoint = f"{self.site_url}/wp-json/wp/v2/categories"

        logger.info(
            "[WordPress Category] lookup name=%s request_url=%s",
            name,
            endpoint,
        )
        logger.info(
            "[WordPress Category] lookup_headers=%s",
            self._redact_headers(dict(self.client.headers)),
        )

        try:
            response = await self._request_with_retry(
                "GET",
                endpoint,
                params={"search": name, "per_page": 100},
                timeout=30,
            )
            logger.info("[WordPress Category] lookup_status=%s", response.status_code)
            logger.info("[WordPress Category] lookup_body=%s", response.text[:4000])
            self._raise_for_status(response)

            raw = response.json()
            if isinstance(raw, dict) and isinstance(raw.get("data"), list):
                candidates = raw["data"]
            elif isinstance(raw, list):
                candidates = raw
            else:
                candidates = []

            for candidate in candidates:
                if not isinstance(candidate, dict):
                    continue
                candidate_name = str(candidate.get("name") or "").strip()
                category_id = candidate.get("id") or candidate.get("term_id")
                if candidate_name.casefold() == name.casefold() and isinstance(category_id, int):
                    logger.info(
                        "[WordPress Category] found name=%s category_id=%s",
                        name,
                        category_id,
                    )
                    return category_id

            logger.info(
                "[WordPress Category] not_found name=%s; creating at request_url=%s",
                name,
                endpoint,
            )
            create_response = await self._request_with_retry(
                "POST",
                endpoint,
                json={"name": name},
                timeout=30,
            )
            logger.info("[WordPress Category] create_status=%s", create_response.status_code)
            logger.info("[WordPress Category] create_body=%s", create_response.text[:4000])

            create_raw = create_response.json()
            # WordPress returns term_exists during a concurrent create; reuse it.
            if create_response.status_code == 400 and isinstance(create_raw, dict):
                existing_id = (
                    create_raw.get("data", {}).get("term_id")
                    if isinstance(create_raw.get("data"), dict)
                    else None
                )
                if isinstance(existing_id, int) and existing_id > 0:
                    logger.info(
                        "[WordPress Category] concurrent_create_reused name=%s category_id=%s",
                        name,
                        existing_id,
                    )
                    return existing_id

            self._raise_for_status(create_response)
            category = (
                create_raw.get("data")
                if isinstance(create_raw, dict) and isinstance(create_raw.get("data"), dict)
                else create_raw
            )
            category_id = (
                category.get("id") or category.get("term_id")
                if isinstance(category, dict)
                else None
            )
            if not isinstance(category_id, int) or category_id <= 0:
                raise RextExternalServiceException(
                    message=(
                        "WordPress category creation response did not contain "
                        f"a valid category ID: {create_raw!r}"
                    ),
                    service_name="WordPress",
                )

            logger.info(
                "[WordPress Category] created name=%s category_id=%s",
                name,
                category_id,
            )
            return category_id
        except RextExternalServiceException:
            raise
        except Exception as exc:
            logger.exception(
                "[WordPress Category] failed name=%s reason=%s",
                name,
                exc,
            )
            raise RextExternalServiceException(
                message=f"Failed to resolve WordPress category '{name}': {exc}",
                service_name="WordPress",
            ) from exc

    async def update_post(self, post_id: int, **kwargs) -> Dict[str, Any]:
        """Update an existing WordPress post."""
        if self.api_key and self.api_endpoint:
            endpoint = f"{self.api_endpoint}/posts/{post_id}"
        else:
            endpoint = f"{self.site_url}/wp-json/wp/v2/posts/{post_id}"

        payload = dict(kwargs)
        if "status" in payload:
            payload["status"] = normalize_wordpress_post_status(payload["status"])
            logger.info(
                "[WordPress Status] update_post_id=%s request_status=%s",
                post_id,
                payload["status"],
            )
        if "categories" in payload and self.api_key and self.api_endpoint:
            payload["post_category"] = payload["categories"]
        if "tags" in payload and self.api_key and self.api_endpoint:
            payload["tags_input"] = payload["tags"]
        # Caller-only hints: WordPress has no such post fields, so they are
        # consumed here rather than sent. featured_media=0 passes through
        # untouched — it is how a previous thumbnail gets removed.
        image_url = payload.pop("image_url", None)
        image_alt_text = payload.pop("image_alt_text", None)
        if payload.get("featured_media") is None and image_url:
            media_info = await self._upload_featured_image(
                image_url,
                alt_text=build_image_alt_text(
                    user_alt=image_alt_text,
                    title=payload.get("title"),
                ),
            )
            if media_info:
                payload["featured_media"] = media_info["media_id"]
                if payload.get("content"):
                    # The theme renders featured_media automatically — drop the inline
                    # copy so the same photo doesn't also appear inside the article body.
                    payload["content"] = self._strip_first_embedded_image(
                        payload["content"], image_url
                    )

        try:
            logger.info("[WordPress Update] payload=%s", payload)
            response = await self._request_with_retry("POST", endpoint, json=payload, timeout=30)
            logger.info("[WordPress Update] response_status=%s", response.status_code)
            logger.info("[WordPress Update] response_body=%s", response.text[:4000])
            self._raise_for_status(response)
            raw = response.json()

            if "status" in payload:
                post = (
                    raw.get("data")
                    if isinstance(raw, dict) and isinstance(raw.get("data"), dict)
                    else raw
                )
                returned_status = post.get("status") if isinstance(post, dict) else None
                if returned_status != payload["status"]:
                    verified_post = await self._fetch_post_for_featured_media(
                        post_id,
                        payload["status"],
                    )
                    verified_status = (
                        verified_post.get("status") if isinstance(verified_post, dict) else None
                    )
                    logger.info(
                        "[WordPress Status] update_verify post_id=%s expected=%s response=%s fetched_post=%s",
                        post_id,
                        payload["status"],
                        returned_status,
                        verified_status,
                    )
                    if verified_status != payload["status"]:
                        raise RextExternalServiceException(
                            message=(
                                "WordPress did not confirm the requested updated post status "
                                f"(post_id={post_id}, sent={payload['status']}, "
                                f"response={returned_status}, fetched_post={verified_status})"
                            ),
                            service_name="WordPress",
                        )

            return raw

        except Exception as e:
            logger.error(f"Failed to update post {post_id}: {e}")
            raise

    async def get_post_status(self, post_id: int) -> Dict[str, Any]:
        """
        Fetch the current status of a WordPress post.

        Returns:
            Dict with 'status' ('publish', 'draft', 'trash', etc.) and 'link'.
            If the post is not found (404), returns status 'deleted'.
        """
        if self.api_key and self.api_endpoint:
            endpoint = f"{self.api_endpoint}/posts/{post_id}"
        else:
            endpoint = f"{self.site_url}/wp-json/wp/v2/posts/{post_id}"

        try:
            response = await self.client.get(endpoint, timeout=15)

            if response.status_code == 404:
                return {"status": "deleted", "success": True}

            response.raise_for_status()
            raw = response.json()
            data = raw.get("data") if isinstance(raw.get("data"), dict) else raw

            return {
                "status": data.get("status"),
                "link": data.get("url") or data.get("link"),
                "success": True,
            }
        except Exception as e:
            logger.error(f"Failed to fetch WordPress post status for {post_id}: {e}")
            return {"status": "unknown", "success": False, "error": str(e)}
