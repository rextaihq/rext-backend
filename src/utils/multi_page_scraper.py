"""
Discovers and scrapes secondary pages (about/team/contact) that commonly
contain founder/team names, which the homepage alone often lacks.
Isolated from the main scraping path — only called explicitly.
"""
import re
from typing import List
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup

from src.api.lib.logger import auto_logger

logger = auto_logger()

_RELEVANT_PATH_KEYWORDS = [
    "about", "team", "our-team", "meet-the-team", "leadership",
    "staff", "people", "founders", "company", "who-we-are",
]

_MAX_EXTRA_PAGES = 3


def discover_relevant_links(html: str, base_url: str) -> List[str]:
    """
    Parse homepage HTML for internal links likely to contain team/founder
    info (About, Team, Leadership, etc). Returns up to _MAX_EXTRA_PAGES
    absolute URLs, deduplicated, excluding the base URL itself.
    """
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    base_netloc = urlparse(base_url).netloc

    found = []
    seen = set()

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith("#") or href.startswith("mailto:"):
            continue

        absolute_url = urljoin(base_url, href)
        parsed = urlparse(absolute_url)

        # Only follow same-domain links
        if parsed.netloc != base_netloc:
            continue

        path_lower = parsed.path.lower()
        link_text = (a.get_text() or "").strip().lower()

        is_relevant = any(
            kw in path_lower or kw in link_text
            for kw in _RELEVANT_PATH_KEYWORDS
        )
        if not is_relevant:
            continue

        normalized = absolute_url.split("#")[0].rstrip("/")
        if normalized == base_url.rstrip("/") or normalized in seen:
            continue

        seen.add(normalized)
        found.append(normalized)

        if len(found) >= _MAX_EXTRA_PAGES:
            break

    logger.info(f"Discovered {len(found)} relevant secondary pages: {found}")
    return found


async def scrape_extra_pages(crawler, urls: List[str], run_config) -> str:
    """
    Scrapes a list of secondary page URLs with an already-open crawler
    instance, and returns their combined markdown content as one string.
    Failures on individual pages are logged and skipped, not raised.
    """
    combined_markdown = []

    for url in urls:
        try:
            result = await crawler.arun(url=url, config=run_config)
            if result.success and result.markdown:
                combined_markdown.append(result.markdown)
            else:
                logger.warning(f"Secondary page scrape failed for {url}")
        except Exception as e:
            logger.warning(f"Error scraping secondary page {url}: {e}")

    return "\n\n".join(combined_markdown)
