"""Fetches product/service subpage content used to seed competitor discovery keywords."""
import logging

from src.config.crawler import CrawlerConfiguration
from src.utils.multi_page_scraper import discover_relevant_links, scrape_extra_pages

logger = logging.getLogger(__name__)

OFFERING_PATH_KEYWORDS = [
    "product", "service", "solution", "platform", "feature",
    "what-we-do", "offering", "category",
]
_MAX_OFFERING_PAGES = 5


async def crawl_offering_subpages(html: str, base_url: str) -> str:
    """Crawl up to _MAX_OFFERING_PAGES product/service pages linked from the homepage.

    Non-fatal: returns "" on any failure so callers can proceed with
    homepage-only content instead of aborting.
    """
    if not html:
        return ""

    offering_links = discover_relevant_links(
        html, base_url, keywords=OFFERING_PATH_KEYWORDS, limit=_MAX_OFFERING_PAGES
    )
    if not offering_links:
        return ""

    try:
        from crawl4ai import AsyncWebCrawler

        config = CrawlerConfiguration()
        async with AsyncWebCrawler(config=config.get_browser_config()) as crawler:
            return await scrape_extra_pages(crawler, offering_links, config.get_run_config())
    except Exception as exc:
        logger.warning("Offering subpage crawl failed (non-fatal): %s", exc)
        return ""
