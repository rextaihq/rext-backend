#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
advertools_fallback.py — second-opinion persona discovery.

WHY THIS EXISTS
    persona_discovery.py walks a site with hand-rolled sitemap parsing and
    httpx. That is fast and precise, but it returns nothing when a site
    publishes its URLs in a shape the hand-rolled parser mishandles: gzipped
    sitemaps, sitemap indexes nested several levels deep, news/image sitemap
    extensions, or a robots.txt that points somewhere unexpected.

    advertools solves exactly that problem and is battle-tested against it,
    so it is used here as an independent second attempt rather than as a
    replacement.

PIPELINE
    1. discover   advertools.sitemap_to_df   -> every URL the site publishes
    2. crawl      advertools.crawl           -> page text, headings, JSON-LD
    3. filter     pandas regex scoring       -> only pages that can hold people
    4. extract    LLM                        -> personas, verbatim-verified

    Step 4 reuses persona_discovery._verify_against_source, so the
    anti-hallucination guarantee is identical: a name the model did not copy
    out of the fetched page is discarded, and any embellished field is nulled.

REACTOR CONSTRAINT
    advertools.crawl runs Scrapy, whose Twisted reactor cannot be restarted
    inside a process. A long-lived API worker would therefore succeed once and
    raise ReactorNotRestartable on every later call, so the crawl always runs
    in a fresh spawned process. sitemap_to_df is plain requests and is safe to
    call in-process.
"""

from __future__ import annotations

import asyncio
import json
import logging
import multiprocessing as mp
import re
import sys
import tempfile
from pathlib import Path
from urllib.parse import urljoin, urlparse

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from persona.persona_discovery import (            # noqa: E402
    LLM_EXTRACT_PROMPT,
    PersonaConfig,
    _verify_against_source,
    registrable_domain,
    same_site,
)

# Words that mark a page as capable of naming people. Used by the pandas
# filter below, against the URL and the title. Kept broad on purpose: this
# stage only RANKS pages, and the LLM plus verbatim verification decide what
# is actually a person.
PEOPLE_URL_RE = (
    r"team|about|people|staff|leader|board|founder|author|contributor|"
    r"writer|editor|expert|management|crew|member|advisor|bio|who-we-are|"
    r"meet|profile|director|officer|blog|news|article|post|insight|story|press"
)

# Job-title vocabulary. A page whose text is dense with these is a roster or
# a byline page, whatever its URL says.
ROLE_TEXT_RE = (
    r"\b(CEO|CTO|COO|CMO|CFO|VP|Vice President|President|Founder|Co-?Founder|"
    r"Director|Manager|Head of|Lead|Chief|Officer|Editor|Writer|Author|"
    r"Journalist|Specialist|Strategist|Consultant|Analyst|Engineer|Designer|"
    r"Architect|Scientist|Researcher|Coordinator|Executive|Partner|Principal)\b"
)


# ============================================================================
# 1. DISCOVER  (advertools.sitemap_to_df)
# ============================================================================

def collect_sitemap_urls(base_url: str, cfg: PersonaConfig):
    """
    Every URL the site publishes, as a DataFrame.

    Tries robots.txt-declared sitemaps first, then the conventional locations,
    on the site and on the publishing subdomains companies habitually use.
    Returns an empty DataFrame rather than raising - this is a fallback path
    and must never be the thing that breaks a workspace build.
    """
    import pandas as pd
    import advertools as adv

    base = registrable_domain(urlparse(base_url).netloc)
    scheme = urlparse(base_url).scheme or "https"

    candidates = [urljoin(base_url, "/robots.txt")]
    for host in [urlparse(base_url).netloc] + [f"{s}.{base}" for s in
                                               ("blog", "news", "insights", "resources")]:
        candidates.append(f"{scheme}://{host}/sitemap.xml")
        candidates.append(f"{scheme}://{host}/sitemap_index.xml")

    frames = []
    for url in candidates:
        try:
            if url.endswith("robots.txt"):
                robots = adv.robotstxt_to_df(url)
                sitemaps = robots.loc[
                    robots["directive"].str.lower() == "sitemap", "content"].tolist()
            else:
                sitemaps = [url]
            for sm in sitemaps:
                try:
                    df = adv.sitemap_to_df(sm, recursive=True)
                    if len(df):
                        frames.append(df)
                except Exception as e:
                    logger.debug("sitemap_to_df(%s): %s", sm, e)
        except Exception as e:
            logger.debug("sitemap discovery %s: %s", url, e)

    if not frames:
        return pd.DataFrame(columns=["loc"])
    out = pd.concat(frames, ignore_index=True)
    if "loc" not in out.columns:
        return pd.DataFrame(columns=["loc"])
    out = out.dropna(subset=["loc"]).drop_duplicates(subset=["loc"])
    out = out[out["loc"].apply(lambda u: same_site(str(u), base))]
    logger.info("[adv 1/4] sitemap_to_df -> %d URLs", len(out))
    return out.reset_index(drop=True)


# ============================================================================
# 2. CRAWL  (advertools.crawl, in a fresh process)
# ============================================================================

def _crawl_worker(urls: list, out_path: str, user_agent: str, timeout: int) -> None:
    """Runs in a spawned process so Scrapy always gets a fresh reactor."""
    try:
        import advertools as adv
        adv.crawl(
            urls,
            out_path,
            follow_links=False,
            custom_settings={
                "USER_AGENT": user_agent,
                "ROBOTSTXT_OBEY": True,
                "CLOSESPIDER_TIMEOUT": timeout,
                "CONCURRENT_REQUESTS": 8,
                "DOWNLOAD_TIMEOUT": 20,
                "LOG_LEVEL": "ERROR",
                "RETRY_TIMES": 1,
            },
        )
    except Exception as exc:                        # pragma: no cover
        print(f"crawl worker failed: {exc}", file=sys.stderr)


async def _httpx_crawl(urls: list, cfg: PersonaConfig):
    """
    Fetch pages with httpx into the same frame shape advertools produces.

    advertools.crawl shells out to the `scrapy` binary, which is a separate
    install. Rather than make the whole fallback depend on that, this backend
    covers the same ground with the HTTP client the project already ships.
    """
    import httpx
    import pandas as pd
    from bs4 import BeautifulSoup

    sem = asyncio.Semaphore(cfg.concurrency)

    async def one(client, url):
        async with sem:
            try:
                r = await client.get(url, headers=cfg.headers(),
                                     timeout=cfg.request_timeout,
                                     follow_redirects=True)
                if r.status_code != 200 or "html" not in r.headers.get(
                        "content-type", "").lower():
                    return None
                soup = BeautifulSoup(r.text, "html.parser")
                for tag in soup.select("script, style, noscript"):
                    tag.decompose()
                grab = lambda sel: " ".join(  # noqa: E731
                    e.get_text(" ", strip=True) for e in soup.select(sel))
                return {
                    "url": url,
                    "status": 200,
                    "title": soup.title.get_text(" ", strip=True) if soup.title else "",
                    "h1": grab("h1"), "h2": grab("h2"), "h3": grab("h3"),
                    "body_text": soup.get_text(" ", strip=True),
                }
            except Exception as e:
                logger.debug("httpx crawl %s: %s", url, e)
                return None

    limits = httpx.Limits(max_connections=cfg.concurrency * 2)
    async with httpx.AsyncClient(limits=limits, follow_redirects=True) as client:
        rows = await asyncio.gather(*[one(client, u) for u in urls],
                                    return_exceptions=True)
    rows = [r for r in rows if isinstance(r, dict)]
    logger.info("[adv 2/4] crawled %d pages (httpx backend)", len(rows))
    return pd.DataFrame(rows)


def _scrapy_available() -> bool:
    import shutil
    return shutil.which("scrapy") is not None


async def crawl_urls(urls: list, cfg: PersonaConfig, timeout: int = 180):
    """
    Crawl `urls` and return the results as a DataFrame (empty on failure).

    Async because the caller already runs inside an event loop - asyncio.run()
    here would raise "cannot be called from a running event loop", and the
    Scrapy path is pushed to a thread so its blocking join cannot stall it.
    """
    import pandas as pd

    if not urls:
        return pd.DataFrame()
    if not _scrapy_available():
        logger.info("scrapy binary absent - using httpx crawl backend")
        return await _httpx_crawl(urls, cfg)
    return await asyncio.to_thread(_scrapy_crawl, urls, cfg, timeout)


def _scrapy_crawl(urls: list, cfg: PersonaConfig, timeout: int):
    import pandas as pd
    out_path = str(Path(tempfile.mkdtemp(prefix="persona_adv_")) / "crawl.jl")
    try:
        ctx = mp.get_context("spawn")
        proc = ctx.Process(target=_crawl_worker,
                           args=(list(urls), out_path, cfg.user_agent, timeout))
        proc.start()
        proc.join(timeout + 60)
        if proc.is_alive():
            proc.terminate()
            proc.join(10)
    except Exception as e:
        logger.warning("advertools crawl process failed: %s", e)
        return pd.DataFrame()

    if not Path(out_path).exists():
        return pd.DataFrame()
    try:
        df = pd.read_json(out_path, lines=True)
    except Exception as e:
        logger.warning("could not read crawl output: %s", e)
        return pd.DataFrame()
    logger.info("[adv 2/4] crawled %d pages", len(df))
    return df


# ============================================================================
# 3. FILTER  (pandas)
# ============================================================================

def rank_people_pages(df, top_n: int = 12):
    """
    Score every crawled page on how likely it is to name people, in pandas.

    Three independent signals, summed:
      url_score    people vocabulary in the path
      title_score  people vocabulary in the <title>
      role_score   density of job titles in the body text

    Ranking rather than filtering is deliberate: a hard filter would drop a
    roster page whose URL and title give nothing away, which is precisely the
    case that defeated the URL-based classifier in the first place.
    """
    import pandas as pd

    if df is None or not len(df):
        return pd.DataFrame()
    work = df.copy()
    for col in ("url", "title", "body_text", "h1", "h2", "h3"):
        if col not in work.columns:
            work[col] = ""
        work[col] = work[col].fillna("").astype(str)

    if "status" in work.columns:
        work = work[work["status"].fillna(200).astype(int) == 200]

    text = (work["body_text"] + " " + work["h1"] + " " + work["h2"]
            + " " + work["h3"])
    work["url_score"] = work["url"].str.contains(PEOPLE_URL_RE, case=False,
                                                 regex=True, na=False).astype(int) * 2
    work["title_score"] = work["title"].str.contains(PEOPLE_URL_RE, case=False,
                                                     regex=True, na=False).astype(int) * 2
    work["role_score"] = text.str.count(ROLE_TEXT_RE).clip(upper=25)
    work["people_score"] = (work["url_score"] + work["title_score"]
                            + work["role_score"])
    # NOT "_text": DataFrame.itertuples() renames any column whose name is not
    # a valid identifier - a leading underscore included - to a positional
    # _1/_2 field, so row._text would silently never resolve.
    work["page_text"] = text.str.replace(r"\s+", " ", regex=True).str.strip()

    ranked = work[(work["people_score"] > 0) & (work["page_text"].str.len() > 200)]
    ranked = ranked.sort_values("people_score", ascending=False).head(top_n)
    logger.info("[adv 3/4] %d candidate pages (top score %s)",
                len(ranked),
                int(ranked["people_score"].iloc[0]) if len(ranked) else 0)
    return ranked.reset_index(drop=True)


# ============================================================================
# 4. EXTRACT  (LLM, verbatim-verified)
# ============================================================================

async def extract_from_pages(model, ranked, cfg: PersonaConfig) -> list:
    """
    Ask the LLM for the people on each ranked page, keep only what is real.

    Every candidate goes through _verify_against_source against that page's
    own crawled text, so this cannot introduce a person the crawler never
    downloaded, and cannot keep a field the page does not state.
    """
    if model is None or ranked is None or not len(ranked):
        return []

    results, seen = [], set()
    for row in ranked.itertuples():
        source = getattr(row, "page_text", "") or ""
        if len(source) < 200:
            continue
        try:
            prompt = LLM_EXTRACT_PROMPT.format(url=row.url, text=source[:8000])
            if hasattr(model, "ainvoke"):
                resp = await model.ainvoke(prompt)
            else:
                resp = await asyncio.to_thread(model.invoke, prompt)
            raw = getattr(resp, "content", None) or str(resp)
            raw = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.M).strip()
            parsed = json.loads(raw)
        except Exception as e:
            logger.debug("adv extraction failed on %s: %s", row.url, e)
            continue
        if not isinstance(parsed, list):
            continue
        for candidate in parsed:
            if not isinstance(candidate, dict):
                continue
            verified = _verify_against_source(candidate, source)
            if not verified:
                logger.info("adv candidate rejected (not verbatim on %s): %r",
                            row.url, candidate.get("name"))
                continue
            key = verified["name"].lower()
            if key in seen:
                continue
            seen.add(key)
            verified["source_url"] = row.url
            results.append(verified)
    logger.info("[adv 4/4] %d verified people", len(results))
    return results


# ============================================================================
# ORCHESTRATION
# ============================================================================

async def discover_via_advertools(base_url: str, cfg: PersonaConfig,
                                  model, max_pages: int = 60) -> list:
    """
    Full fallback run. Returns verified person dicts, or [] - never raises.

    Called only when the primary pipeline found nobody, so its cost is paid
    on exactly the sites that would otherwise return an empty workspace.
    """
    try:
        import pandas as pd  # noqa: F401
        import advertools    # noqa: F401
    except ImportError as e:
        logger.warning("advertools fallback unavailable: %s", e)
        return []

    try:
        urls_df = collect_sitemap_urls(base_url, cfg)
        urls = urls_df["loc"].astype(str).tolist() if len(urls_df) else []
        # The homepage is always worth crawling; a site with no sitemap at all
        # still gets one shot at its landing page.
        urls = [base_url] + [u for u in urls if u != base_url]

        # Cheap pre-rank on the URL alone, so the crawl budget is spent on
        # pages that can plausibly name someone.
        import re as _re
        people_first = [u for u in urls if _re.search(PEOPLE_URL_RE, u, _re.I)]
        others = [u for u in urls if u not in set(people_first)]
        selected = (people_first + others)[:max_pages]

        crawled = await crawl_urls(selected, cfg)
        ranked = rank_people_pages(crawled)
        return await extract_from_pages(model, ranked, cfg)
    except Exception as exc:                        # noqa: BLE001
        logger.warning("advertools fallback failed (non-fatal): %s", exc)
        return []


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    target = sys.argv[1] if len(sys.argv) > 1 else "https://www.wpbeginner.com/"
    try:
        from src.flow.model.llm_manager import load_model
        _model = load_model()
    except Exception as _e:
        print(f"LLM unavailable: {_e}")
        _model = None
    people = asyncio.run(discover_via_advertools(target, PersonaConfig(), _model))
    print(f"\n{len(people)} verified people from {target}\n" + "=" * 70)
    for _p in people:
        print(f"  {_p['name']:28} {_p['role'] or '-'}")
        if _p["socials"]:
            print(f"      {_p['socials']}")
