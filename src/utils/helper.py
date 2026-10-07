# === Standard library imports ===
import asyncio
import contextvars
import sys
import threading
import uuid
from concurrent.futures import Future
from typing import Any, Callable, Coroutine, Dict, List, Optional, Tuple, TypeVar

# === Third-party imports ===
from crawl4ai import AsyncWebCrawler, BrowserConfig, CacheMode, CrawlerRunConfig
from langchain_core.documents import Document

from src.api.lib.logger import auto_logger

# === Project-specific imports ===
from src.utils.browser_guard import PROXY_BROWSER_ARGS, PublicOnlyProxy
from src.utils.content_quality import assess_content_quality, build_thin_content_document
from src.utils.multi_page_scraper import discover_relevant_links, scrape_extra_pages
from src.utils.splitter import split_data
from src.utils.url_validator import validate_url_for_ssrf

logger = auto_logger()


def _browser_config(proxy: PublicOnlyProxy) -> BrowserConfig:
    """A normal headless Chromium (no stealth) whose every connection goes through ``proxy``,
    which lets it reach public addresses only (G88, revnix/rext-control#661)."""
    return BrowserConfig(
        headless=True,
        enable_stealth=False,
        browser_type="chromium",
        viewport_width=1280,
        viewport_height=800,
        # crawl4ai's default is True: a certificate error is a refusal, as it is for httpx.
        ignore_https_errors=False,
        proxy_config={"server": proxy.url},
        extra_args=PROXY_BROWSER_ARGS,
    )


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
        except BaseException as exc:
            result.set_exception(exc)
        finally:
            loop.close()

    threading.Thread(target=_runner, daemon=True).start()
    return asyncio.wrap_future(result)


def _looks_blocked(markdown: str) -> bool:
    """Heuristic check: is this a cookie wall or bot challenge page?"""
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


async def render_pages(
    urls: List[str],
    *,
    budget_seconds: float,
    expand: Optional[Callable[[str, str], List[str]]] = None,
    max_pages: int = 10,
    concurrency: int = 4,
) -> Dict[str, str]:
    """Render specific pages in one headless browser and return url -> HTML.

    Used for pages a site refused to plain HTTP (403, bot challenge). Every URL
    is SSRF-checked, no new page starts once ``budget_seconds`` is spent, and
    the pages that finished are returned. This is a normal browser (no stealth):
    a page that still answers with a bot challenge is dropped, not bypassed.
    ``expand(url, html)`` may name more URLs to render in the same session,
    e.g. the posts listed on a refused blog index.
    """
    from src.utils.fast_scraper import _CHALLENGE_TITLE_RE, BLOCKED_STATUS

    loop = asyncio.get_event_loop()
    deadline = loop.time() + budget_seconds

    def _allowed(url: str) -> bool:
        try:
            validate_url_for_ssrf(url)
            return True
        except Exception:
            logger.warning("Skipping browser render of a disallowed URL", extra={"url": url})
            return False

    queue = [u for u in dict.fromkeys(urls) if _allowed(u)][:max_pages]
    if not queue or budget_seconds <= 0:
        return {}

    run_config = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        page_timeout=int(max(3.0, min(12.0, budget_seconds)) * 1000),
        delay_before_return_html=0.5,
    )

    async def _crawl() -> Dict[str, str]:
        rendered: Dict[str, str] = {}
        seen = set(queue)
        sem = asyncio.Semaphore(concurrency)
        async with (
            PublicOnlyProxy() as proxy,
            AsyncWebCrawler(config=_browser_config(proxy)) as crawler,
        ):

            async def _one(url: str) -> Tuple[str, str]:
                async with sem:
                    if loop.time() >= deadline:
                        return url, ""
                    try:
                        outcome = await crawler.arun(url=url, config=run_config)
                    except Exception as exc:
                        logger.warning(
                            "Browser render failed", extra={"url": url, "error": str(exc)}
                        )
                        return url, ""
                # arun returns a result container that forwards to its first result.
                if not getattr(outcome, "success", False):
                    return url, ""
                status = getattr(outcome, "status_code", None)
                html = str(getattr(outcome, "html", "") or "")
                # crawl4ai reports success for any page that loaded, including a
                # 403 block page, so the HTTP status is checked as well.
                if status in BLOCKED_STATUS or not html or _CHALLENGE_TITLE_RE.search(html[:4000]):
                    logger.info("Browser was refused as well", extra={"url": url, "status": status})
                    return url, ""
                return url, html

            pending = {asyncio.ensure_future(_one(u)) for u in queue}
            started = len(pending)
            while pending:
                remaining = deadline - loop.time()
                if remaining <= 0:
                    break
                done, pending = await asyncio.wait(
                    pending, timeout=remaining, return_when=asyncio.FIRST_COMPLETED
                )
                for task in done:
                    if task.cancelled() or task.exception() is not None:
                        continue
                    url, html = task.result()
                    if not html:
                        continue
                    rendered[url] = html
                    if expand is None:
                        continue
                    try:
                        extras = expand(url, html) or []
                    except Exception:
                        extras = []
                    for extra in extras:
                        if started >= max_pages:
                            break
                        if extra in seen or not _allowed(extra):
                            continue
                        seen.add(extra)
                        started += 1
                        pending.add(asyncio.ensure_future(_one(extra)))
            for task in pending:
                task.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
        return rendered

    return await _run_on_proactor_loop(_crawl)


async def web_page_scraper(urls: list[str]) -> tuple[list, list]:
    """Render publicly accessible pages without evading site access controls."""
    if not urls:
        return [], []

    target_url = urls[0]
    extra_content = ""

    # Fast initial run config (16s cap to respect pipeline budget)
    run_config = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        page_timeout=16000,
        delay_before_return_html=1.5,
        wait_for="css:body",
    )

    async def _crawl() -> list:
        nonlocal extra_content
        async with (
            PublicOnlyProxy() as proxy,
            AsyncWebCrawler(config=_browser_config(proxy)) as crawler,
        ):
            results = await crawler.arun(url=target_url, config=run_config)

            first = next((r for r in results if getattr(r, "success", False)), None)
            if first is None or _looks_blocked(getattr(first, "markdown", "") or ""):
                logger.warning(
                    "Page is unavailable to the scraper; respecting the site's access controls",
                    extra={"url": target_url},
                )

            # Secondary multi-page link discovery
            try:
                if (
                    first is not None
                    and first.success
                    and getattr(first, "html", None)
                    and not _looks_blocked(getattr(first, "markdown", "") or "")
                ):
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
            if _looks_blocked(getattr(result, "markdown", "") or ""):
                logger.warning(
                    "Discarding blocked/challenge response",
                    extra={"url": getattr(result, "url", target_url)},
                )
                continue
            assessment = assess_content_quality(result)
            if assessment.get("is_thin"):
                documents.append(build_thin_content_document(result, assessment))
                continue

            doc = Document(
                page_content=result.markdown + ("\n\n" + extra_content if extra_content else ""),
                metadata={
                    "id": str(uuid.uuid4()),
                    "url": result.url,
                    "title": result.metadata.get("title", "No title found")
                    if result.metadata
                    else "No title found",
                    "description": result.metadata.get("description", "No description found")
                    if result.metadata
                    else "No description found",
                    "keywords": result.metadata.get("keywords", "No keywords found")
                    if result.metadata
                    else "No keywords found",
                    "summary": result.metadata.get("summary", "No summary found")
                    if result.metadata
                    else "No summary found",
                },
            )
            documents.append(doc)
        else:
            logger.warning(
                f"Scraping failed for {result.url}: {getattr(result, 'error_message', 'Unknown error')}"
            )

    chunks_data = split_data(documents)
    return chunks_data, results
