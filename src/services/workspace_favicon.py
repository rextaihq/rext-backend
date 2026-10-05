"""
The favicon of a workspace's site: found in its homepage, fetched once, kept in the media store.

The dashboard shows it beside the workspace's name in the switcher. Every step
is best-effort: a site without a usable icon leaves the workspace without one,
and the dashboard shows the workspace's initials instead.

The icon is fetched from an address the customer typed, so each request,
redirects included, passes the same SSRF check as the site scraper; the body is
capped, and only raster images that Pillow can read are kept (no SVG, which can
carry script).
"""

import asyncio
import io
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse

import filetype
import httpx
from bs4 import BeautifulSoup
from PIL import Image

from src.utils.logger import logger
from src.utils.url_validator import SSRFValidationError, validate_url_for_ssrf

MAX_FAVICON_BYTES = 256 * 1024
MAX_REDIRECTS = 3
MAX_CANDIDATES = 4
FAVICON_TIMEOUT = 10

# The image types kept, with the extension each is stored under.
FAVICON_TYPES = {
    "image/png": "png",
    "image/x-icon": "ico",
    "image/vnd.microsoft.icon": "ico",
    "image/gif": "gif",
    "image/jpeg": "jpg",
    "image/webp": "webp",
}

_ICON_RELS = {"icon", "apple-touch-icon", "apple-touch-icon-precomposed"}


def _declared_size(link: Any) -> int:
    """The largest square size a <link sizes="…"> declares, or 0."""
    best = 0
    for size in str(link.get("sizes") or "").lower().split():
        width, _, height = size.partition("x")
        if width.isdigit() and width == height:
            best = max(best, int(width))
    return best


def favicon_candidates(html: Optional[str], page_url: str) -> List[str]:
    """Icon addresses the homepage declares, best first, then the conventional /favicon.ico.

    Best is a declared size from 32 to 256 px, larger first; then the rest, larger
    first; an apple-touch-icon with no size counts as 180 px, any other icon as 16.
    """
    scored: List[Tuple[Tuple[int, int], str]] = []
    if html:
        for link in BeautifulSoup(html, "html.parser").find_all("link", href=True):
            rels = {rel.lower() for rel in (link.get("rel") or [])}
            if not rels & _ICON_RELS:
                continue
            href = str(link["href"]).strip()
            if "svg" in str(link.get("type") or "").lower() or href.lower().split("?")[0].endswith(
                ".svg"
            ):
                continue
            url = urljoin(page_url, href)
            if urlparse(url).scheme not in ("http", "https"):
                continue
            size = _declared_size(link) or (180 if "icon" not in rels else 16)
            scored.append(((0 if 32 <= size <= 256 else 1, -size), url))

    candidates: List[str] = []
    for url in [url for _, url in sorted(scored, key=lambda item: item[0])] + [
        urljoin(page_url, "/favicon.ico")
    ]:
        if url not in candidates:
            candidates.append(url)
    return candidates


def _validated(data: bytes) -> Optional[Tuple[bytes, str]]:
    """The body and its type, when it is a raster image Pillow can read."""
    kind = filetype.guess(data)
    mime = kind.mime if kind else None
    if mime not in FAVICON_TYPES:
        return None
    try:
        Image.open(io.BytesIO(data)).verify()
    except Exception:  # noqa: BLE001 - a decoder refusing it is the answer
        return None
    return data, mime


async def fetch_favicon(
    url: str, *, transport: Optional[httpx.AsyncBaseTransport] = None
) -> Optional[Tuple[bytes, str]]:
    """Fetch one icon address, following at most three redirects, each one SSRF-checked.

    Raises SSRFValidationError for an address on a private or reserved network
    and httpx.HTTPError for a failed request; returns None for anything that is
    not a usable icon.
    """
    async with httpx.AsyncClient(
        transport=transport,
        follow_redirects=False,
        timeout=FAVICON_TIMEOUT,
        headers={"Accept": "image/*", "User-Agent": "RextAI-Favicon/1.0"},
    ) as client:
        for _ in range(MAX_REDIRECTS + 1):
            await asyncio.to_thread(validate_url_for_ssrf, url)
            async with client.stream("GET", url) as response:
                if response.is_redirect:
                    location = response.headers.get("location")
                    if not location:
                        return None
                    url = urljoin(url, location)
                    continue
                if response.status_code != 200:
                    return None
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    body.extend(chunk)
                    if len(body) > MAX_FAVICON_BYTES:
                        return None
                return _validated(bytes(body))
    return None


async def find_favicon(
    html: Optional[str],
    page_url: str,
    *,
    transport: Optional[httpx.AsyncBaseTransport] = None,
) -> Optional[Dict[str, Any]]:
    """The first usable icon among the homepage's candidates, or None. Never raises."""
    for candidate in favicon_candidates(html, page_url)[:MAX_CANDIDATES]:
        try:
            found = await fetch_favicon(candidate, transport=transport)
        except SSRFValidationError as exc:
            logger.info("[Favicon] refused %s: %s", candidate, exc)
            continue
        except httpx.HTTPError as exc:
            logger.info("[Favicon] %s failed: %s", candidate, type(exc).__name__)
            continue
        if found:
            data, mime = found
            return {"data": data, "mime": mime, "source_url": candidate}
    return None


async def store_favicon(workspace_id: str, data: bytes, mime: str) -> Optional[str]:
    """Keep the icon in the media store; returns its object name, or None if storage failed."""
    from src.utils.storage import storage_service

    stamp = int(datetime.now(timezone.utc).timestamp())
    object_name = f"workspaces/{workspace_id}/favicon_{stamp}.{FAVICON_TYPES[mime]}"
    # boto3 blocks, so the upload runs off the event loop.
    uploaded = await asyncio.to_thread(
        storage_service.upload_file, file_data=data, object_name=object_name, content_type=mime
    )
    return object_name if uploaded else None
