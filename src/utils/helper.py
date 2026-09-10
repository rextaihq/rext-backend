# === Standard library imports ===
import asyncio
import contextvars
import sys
import threading
import uuid
from concurrent.futures import Future
from typing import Any, Callable, Coroutine, List, Tuple, TypeVar

# === Third-party imports ===
from crawl4ai import AsyncWebCrawler
from langchain_core.documents import Document
from pydantic import HttpUrl

from src.api.lib.logger import auto_logger
from src.config.crawler import CrawlerConfiguration

# === Project-specific imports ===
# imports from content_quality.py
from src.utils.content_quality import assess_content_quality, build_thin_content_document

# for scraping many pages
from src.utils.multi_page_scraper import discover_relevant_links, scrape_extra_pages
from src.utils.splitter import split_data
from src.utils.url_validator import validate_url_for_ssrf

logger = auto_logger()

# Boilerplate that shows up on cookie-consent walls (OneTrust, Cookiebot, Osano,
# Didomi, ...) and bot-firewall challenge pages (Cloudflare, PerimeterX, Akamai,
# ...) when the real page content never rendered/was withheld. These return a
# normal HTTP 200, so `result.success` alone won't catch them -- only the
# content itself gives it away.
_BLOCKED_CONTENT_MARKERS = (
    "just a moment",
    "checking your browser",
    "attention required",
    "cf-browser-verification",
    "enable javascript and cookies to continue",
    "please verify you are a human",
    "verify you are human",
    "access denied",
    "manage cookie preferences",
    "manage your privacy choices",
    "we use cookies to",
    "accept all cookies",
    "cookie consent",
    "your privacy choices",
)
_BLOCKED_WORD_COUNT_THRESHOLD = 150

_T = TypeVar("_T")


def _run_on_proactor_loop(
    coro_factory: Callable[[], Coroutine[Any, Any, _T]],
) -> "asyncio.Future[_T]":
    """Run ``coro_factory()`` to completion on a dedicated thread with its own
    ProactorEventLoop, and return an awaitable for the result.

    Playwright (used by crawl4ai) launches its browser driver via asyncio
    subprocess transports, which only ProactorEventLoop supports on Windows.
    The app's main event loop, however, must stay on
    WindowsSelectorEventLoopPolicy for psycopg's async connection pool (see
    src/api/server.py) -- the two policies can't coexist on one loop. Building
    the Proactor loop directly here (bypassing the global policy) lets the
    crawl run with subprocess support without disturbing the main loop.
    """
    if not sys.platform.startswith("win"):
        return asyncio.ensure_future(coro_factory())

    loop = asyncio.ProactorEventLoop()
    ctx = contextvars.copy_context()
    result: "Future[_T]" = Future()

    def _runner() -> None:
        asyncio.set_event_loop(loop)
        try:
            value = ctx.run(loop.run_until_complete, coro_factory())
            result.set_result(value)
        except BaseException as exc:  # propagate to the awaiting caller
            result.set_exception(exc)
        finally:
            loop.close()

    threading.Thread(target=_runner, daemon=True).start()
    return asyncio.wrap_future(result)


def _looks_blocked(markdown: str) -> bool:
    """Heuristic check: is this a cookie-consent wall / bot challenge page
    rather than real site content?

    A page stuck behind a GDPR consent wall or a bot-firewall interstitial
    still "succeeds" at the HTTP level, so the only signal available is the
    content itself -- either suspiciously short, or dominated by known
    boilerplate phrases relative to how little real content surrounds them.
    """
    if not markdown or not markdown.strip():
        return True
    text = markdown.strip().lower()
    word_count = len(text.split())
    if word_count < _BLOCKED_WORD_COUNT_THRESHOLD:
        return True
    if word_count < _BLOCKED_WORD_COUNT_THRESHOLD * 3 and any(
        marker in text for marker in _BLOCKED_CONTENT_MARKERS
    ):
        return True
    return False


async def web_page_scraper(urls: List[HttpUrl]) -> Tuple[List[Document], list]:
    """
        Asynchronously crawls given URLs and returns LangChain Documents with extracted content.

        Args:
            urls (List[HttpUrl]): List of URLs to crawl.

        Returns:
            Tuple[List[Document], list]: (Chunked Documents, Raw crawl results)

    Raises:
        : If any URL fails SSRF validation.
    """
    logger.info("Scraping started")
    config = CrawlerConfiguration()
    browser_config = config.get_browser_config()
    run_config = config.get_run_config()

    # Validate all URLs for SSRF before scraping
    validated_urls = []
    for url in urls:
        url_str = str(url)
        validate_url_for_ssrf(url_str)
        validated_urls.append(url_str)

    target_url = validated_urls[0]
    # extra_content is ALWAYS defined here, regardless of which path below
    # executes -- avoids a NameError if secondary-page discovery never runs.
    extra_content = ""

    async def _crawl() -> list:
        nonlocal extra_content
        async with AsyncWebCrawler(config=browser_config) as crawler:
            results = await crawler.arun(url=target_url, config=run_config)

            first = next((r for r in results if getattr(r, "success", False)), None)
            if first is None or _looks_blocked(getattr(first, "markdown", "") or ""):
                logger.warning(
                    "Initial scrape looks blocked (cookie wall / bot challenge / "
                    "empty content) -- retrying with stealth + cookie-dismiss pass",
                    extra={"url": target_url},
                )
                try:
                    fallback_config = config.get_run_config(aggressive=True)
                    # Hard ceiling so a stubborn site can never hang the workspace
                    # pipeline -- the aggressive pass (simulate_user/magic) has its
                    # own internal page_timeout, but this is a belt-and-braces cap
                    # on the whole retry call.
                    retried = await asyncio.wait_for(
                        crawler.arun(url=target_url, config=fallback_config),
                        timeout=60,
                    )
                    retried_first = next((r for r in retried if getattr(r, "success", False)), None)
                    # Only swap in the retry if it actually recovered more content --
                    # never let a worse/failed retry regress a partially-successful
                    # first pass.
                    if retried_first is not None and not _looks_blocked(
                        getattr(retried_first, "markdown", "") or ""
                    ):
                        logger.info(
                            "Fallback scrape recovered real content",
                            extra={"url": target_url},
                        )
                        results = retried
                        first = retried_first
                    else:
                        logger.warning(
                            "Fallback scrape still looks blocked -- proceeding with "
                            "best available result",
                            extra={"url": target_url},
                        )
                except asyncio.TimeoutError:
                    logger.warning(
                        "Fallback scrape timed out -- proceeding with original result",
                        extra={"url": target_url},
                    )

            # --- Multi-page discovery: runs ONCE, inside this same crawler
            # session, using whichever result actually succeeded above
            # (original or the aggressive retry). Non-fatal if it fails. ---
            try:
                if first is not None and first.success and getattr(first, "html", None):
                    extra_links = discover_relevant_links(first.html, target_url)
                    if extra_links:
                        extra_content = await scrape_extra_pages(crawler, extra_links, run_config)
            except Exception as e:
                logger.warning(f"Secondary page discovery/scrape failed: {e}")

            return results

    results = await _run_on_proactor_loop(_crawl)
    logger.info("Scraping completed")

    documents = []
    for result in results:
        if result.success:
            assessment = assess_content_quality(result)
            if assessment["is_thin"]:
                documents.append(build_thin_content_document(result, assessment))
                continue

            doc = Document(
                page_content=result.markdown + ("\n\n" + extra_content if extra_content else ""),
                metadata={
                    "id": str(uuid.uuid4()),
                    "url": result.url,
                    "title": result.metadata.get("title", "No title found"),
                    "description": result.metadata.get("description", "No description found"),
                    "keywords": result.metadata.get("keywords", "No keywords found"),
                    "summary": result.metadata.get("summary", "No summary found"),
                },
            )
            documents.append(doc)
        else:
            logger.warning(f"Scraping failed for {result.url}: {result.error_message}")

    chunks_data = split_data(documents)

    return chunks_data, results
