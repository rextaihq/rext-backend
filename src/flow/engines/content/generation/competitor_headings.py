"""The ranking pages' headings, for the outline gate's Sources view (rext-control#476).

The SERP step reads titles, snippets and links only. Before the outline is written, this
node reads the top ranking pages once per run and keeps their H2 and H3 text in order, so the
dashboard can show what the competing articles cover beside the planned outline. It doesn't
change the outline: using the headings to plan it is a separate decision.

The pages are third-party addresses from the search results, so every request, redirects
included, passes the same SSRF check as the site scraper. Each body is capped, each page has a
short timeout, and the pages are read side by side. A page that times out, blocks, redirects
too often or isn't HTML is left out; nothing here can fail the run.

It is off unless OUTLINE_COMPETITOR_HEADINGS=true: reading the pages adds up to PAGE_TIMEOUT
seconds (6) to every run before its outline, usually one to three, since the five pages are
read at once. With it off, the gate's Sources show no headings.
"""

import asyncio
import os
import re
from typing import Any, Dict, List, Optional

import httpx
from bs4 import BeautifulSoup

from src.utils.logger import logger
from src.utils.url_validator import SSRFValidationError, validate_url_for_ssrf

MAX_PAGES = 5
PAGE_TIMEOUT = 6
MAX_PAGE_BYTES = 2 * 1024 * 1024
MAX_REDIRECTS = 3
MAX_HEADINGS_PER_PAGE = 40
MAX_HEADING_CHARS = 200
USER_AGENT = "Mozilla/5.0 (compatible; RextAI-Research/1.0; +https://rext.ai)"


def competitor_headings_enabled() -> bool:
    """Whether a run reads the ranking pages' headings before its outline (off by default)."""
    return os.getenv("OUTLINE_COMPETITOR_HEADINGS", "false").strip().lower() == "true"


def extract_headings(html: str) -> List[Dict[str, Any]]:
    """A page's H2 and H3 text, in the page's order, without empty or repeated ones."""
    soup = BeautifulSoup(html, "html.parser")
    for hidden in soup(["script", "style", "noscript", "template", "nav", "footer"]):
        hidden.decompose()
    headings: List[Dict[str, Any]] = []
    seen = set()
    for tag in soup.find_all(["h2", "h3"]):
        text = re.sub(r"\s+", " ", tag.get_text(" ", strip=True)).strip()[:MAX_HEADING_CHARS]
        key = (tag.name, text.lower())
        if not text or key in seen:
            continue
        seen.add(key)
        headings.append({"level": int(tag.name[1]), "text": text})
        if len(headings) == MAX_HEADINGS_PER_PAGE:
            break
    return headings


async def _get_html(client: httpx.AsyncClient, url: str) -> Optional[str]:
    """GET a page, following at most three redirects, each one SSRF-checked.

    None for anything but an HTML 200 under the size cap; raises for a refused address or a
    failed request, which the caller skips.
    """
    for _ in range(MAX_REDIRECTS + 1):
        await asyncio.to_thread(validate_url_for_ssrf, url)
        async with client.stream("GET", url) as response:
            if response.is_redirect:
                location = response.headers.get("location")
                if not location:
                    return None
                url = str(response.url.join(location))
                continue
            if response.status_code != 200:
                return None
            if "html" not in response.headers.get("content-type", "").lower():
                return None
            body = bytearray()
            async for chunk in response.aiter_bytes():
                body.extend(chunk)
                if len(body) > MAX_PAGE_BYTES:
                    return None
            return body.decode(response.encoding or "utf-8", errors="replace")
    return None


async def _page_headings(
    client: httpx.AsyncClient, result: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    url = str(result.get("url") or "")
    try:
        html = await asyncio.wait_for(_get_html(client, url), timeout=PAGE_TIMEOUT)
    except (SSRFValidationError, httpx.HTTPError, asyncio.TimeoutError, ValueError):
        return None
    except Exception:  # noqa: BLE001 - one page never stops the others
        logger.warning("A ranking page could not be read", exc_info=True)
        return None
    if not html:
        return None
    # Parsing is CPU work: off the event loop, as the fetches are.
    headings = await asyncio.to_thread(extract_headings, html)
    if not headings:
        return None
    return {"url": url, "title": result.get("title") or "", "headings": headings}


async def fetch_competitor_headings(
    results: List[Dict[str, Any]],
    *,
    transport: Optional[httpx.AsyncBaseTransport] = None,
) -> List[Dict[str, Any]]:
    """The headings of the top ranking pages, in their ranking order; unreadable pages left out."""
    ranked = sorted(
        (r for r in results if isinstance(r, dict) and str(r.get("url") or "").startswith("http")),
        key=lambda r: r.get("position") or 0,
    )[:MAX_PAGES]
    if not ranked:
        return []
    async with httpx.AsyncClient(
        transport=transport,
        follow_redirects=False,
        timeout=PAGE_TIMEOUT,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html"},
    ) as client:
        pages = await asyncio.gather(*(_page_headings(client, r) for r in ranked))
    return [page for page in pages if page]


async def read_competitor_headings(state) -> Dict[str, Any]:
    """The graph node: read the ranking pages once per run, before the outline is written.

    A regenerated outline comes back through generate_outline, not here, and a resumed run
    that already has them doesn't read them again.
    """
    content = state.get("content") or {}
    if content.get("competitor_headings") is not None:
        return {}
    if not competitor_headings_enabled():
        return {"content": {"competitor_headings": []}}
    normalized = state.get("serp_normalized")
    results = (normalized or {}).get("normalize_results") if isinstance(normalized, dict) else []
    try:
        headings = await fetch_competitor_headings(list(results or []))
    except Exception:  # noqa: BLE001 - the Sources view is optional; the run goes on
        logger.warning("The ranking pages' headings could not be read", exc_info=True)
        headings = []
    return {"content": {"competitor_headings": headings}}
