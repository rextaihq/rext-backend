"""Homepage + internal-page scraping for competitor discovery.

Thin wrapper over src/utils/fast_scraper.py (the shared, browser-free scraper),
pinned to this module's original behavior: homepage + up to MAX_INTERNAL_PAGES
about/product/etc. subpages, footer stripped, no blog/news crawl. Workspace
brand-voice/persona extraction (src/services/workspace_pipeline.py) uses the
same underlying fast_scraper directly, with different settings (footer kept,
blog/news crawl enabled) — this module's behavior is unaffected by that.
"""
from typing import Dict

from src.flow.engines.competitors.constants import MAX_INTERNAL_PAGES
from src.utils.fast_scraper import USER_AGENT, fetch, visible_text
from src.utils.fast_scraper import scrape_site as _fast_scrape_site

__all__ = ["USER_AGENT", "fetch", "visible_text", "scrape_site"]


async def scrape_site(url: str) -> Dict[str, str]:
    result = await _fast_scrape_site(
        url,
        max_about_pages=MAX_INTERNAL_PAGES,
        home_max_chars=3000,
        about_max_chars=3000,
        max_blog_posts=0,
        strip_footer=True,
    )
    return result["pages"]
