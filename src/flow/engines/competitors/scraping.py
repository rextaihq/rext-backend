"""Homepage + internal-page scraping, ported from the reference Colab notebook.

Uses httpx instead of the notebook's aiohttp — this codebase's established async
HTTP client (already used identically for the DataForSEO SERP integration in
src/flow/engines/serp/fetch_serp.py) — with equivalent semaphore-bounded
concurrency and timeouts. Behavior is otherwise unchanged from the notebook.
"""
import asyncio
import re
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from src.flow.engines.competitors.constants import CONCURRENCY, MAX_INTERNAL_PAGES, REQUEST_TIMEOUT
from src.flow.engines.competitors.domain_utils import normalize_domain

USER_AGENT = "Mozilla/5.0 (compatible; CompetitorBot/1.0)"


def visible_text(html: str, max_chars: int = 3000) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "header", "footer", "nav"]):
        tag.decompose()
    text = re.sub(r"\s+", " ", soup.get_text(" ")).strip()
    return text[:max_chars]


def find_internal_links(html: str, base_url: str) -> list:
    soup = BeautifulSoup(html, "html.parser")
    keywords = ("about", "product", "service", "solution", "pricing", "platform", "feature")
    base_domain = normalize_domain(base_url)
    candidates = []
    for a in soup.find_all("a", href=True):
        href = urljoin(base_url, a["href"])
        parsed = urlparse(href)
        if normalize_domain(href) != base_domain:
            continue
        path = parsed.path.lower()
        if any(k in path for k in keywords):
            candidates.append(href.split("#")[0])
    seen, out = set(), []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out[:MAX_INTERNAL_PAGES]


async def fetch(client: httpx.AsyncClient, url: str, sem: asyncio.Semaphore) -> str:
    try:
        async with sem:
            resp = await client.get(url, timeout=REQUEST_TIMEOUT)
            if resp.status_code == 200 and "text/html" in resp.headers.get("content-type", ""):
                return resp.text
    except Exception:
        pass
    return ""


async def scrape_site(url: str) -> dict:
    sem = asyncio.Semaphore(CONCURRENCY)
    headers = {"User-Agent": USER_AGENT}
    async with httpx.AsyncClient(headers=headers, verify=False, follow_redirects=True) as client:
        home_html = await fetch(client, url, sem)
        internal_links = find_internal_links(home_html, url) if home_html else []
        pages_html = await asyncio.gather(*[fetch(client, link, sem) for link in internal_links])

    pages = {url: visible_text(home_html)} if home_html else {}
    for link, html in zip(internal_links, pages_html):
        if html:
            pages[link] = visible_text(html)
    return pages
