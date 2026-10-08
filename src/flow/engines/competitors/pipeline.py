"""Orchestrates SERP-based competitor discovery, ported from the reference Colab
notebook's ``find_competitors``:

    scrape_site -> summarize_business -> generate_queries -> run_all_searches
    -> mine_all_listicles -> aggregate_candidates -> classify_all
    -> confirmed competitors, sorted by frequency desc / confidence desc

Pure orchestration — no DB/SSE concerns — matching the notebook's own structure.
Returns plain dict/list structures instead of the notebook's pandas DataFrame,
which was a Colab display detail, not part of the algorithm.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional

from src.flow.engines.competitors.aggregation import aggregate_candidates
from src.flow.engines.competitors.classification import classify_all
from src.flow.engines.competitors.constants import (
    DIRECT_CONFIDENCE_THRESHOLD,
    MAX_DISPLAY_COMPETITORS,
    MAX_QUERIES,
    MIN_DISPLAY_COMPETITORS,
)
from src.flow.engines.competitors.domain_utils import is_same_brand_or_domain
from src.flow.engines.competitors.listicle import mine_all_listicles
from src.flow.engines.competitors.llm_client import generate_queries, summarize_business
from src.flow.engines.competitors.scraping import scrape_site
from src.flow.engines.competitors.serp import run_all_searches

logger = logging.getLogger(__name__)

# Told where the discovery is, for whoever shows it while it runs (the workspace's
# creation screen, revnix/rext-control#845): {"stage": "searching", "queries": 8},
# then {"stage": "checking", "candidates": 34}.
ProgressCallable = Callable[[Dict[str, Any]], Awaitable[None]]


async def _say(on_progress: Optional[ProgressCallable], progress: Dict[str, Any]) -> None:
    """Report progress, never at the discovery's cost."""
    if on_progress is None:
        return
    try:
        await on_progress(progress)
    except Exception:  # noqa: BLE001 - a listener that fails must not stop the discovery
        logger.warning("Competitor discovery: a progress listener failed", exc_info=True)


async def discover_competitors(
    site_url: str, on_progress: Optional[ProgressCallable] = None
) -> Dict[str, Any]:
    """Faithful port of the notebook's find_competitors(site_url)."""
    pages = await scrape_site(site_url)
    logger.info("Competitor discovery: scraped %d page(s) for %s", len(pages), site_url)

    summary = await summarize_business(site_url, pages)
    logger.info(
        "Competitor discovery: business summary for %s — %s / %s",
        site_url,
        summary.get("company_name"),
        summary.get("category"),
    )

    query_sets = await generate_queries(summary)
    queries = (query_sets.get("category_queries", []) + query_sets.get("brand_queries", []))[
        :MAX_QUERIES
    ]
    logger.info("Competitor discovery: generated %d queries: %s", len(queries), queries)

    await _say(on_progress, {"stage": "searching", "queries": len(queries)})
    serp_results = await run_all_searches(queries)
    logger.info("Competitor discovery: got %d raw SERP results", len(serp_results))

    mined_domains = await mine_all_listicles(serp_results)
    logger.info("Competitor discovery: mined %d domains from listicles", len(mined_domains))

    company_name = summary.get("company_name", "")
    candidates = aggregate_candidates(
        site_url, serp_results, mined_domains, company_name=company_name
    )
    logger.info(
        "Competitor discovery: %d unique candidates going to classification", len(candidates)
    )

    await _say(on_progress, {"stage": "checking", "candidates": len(candidates)})
    classifications = await classify_all(summary, candidates)

    rows = []
    for domain, ev in candidates.items():
        c = classifications.get(domain, {})
        rows.append(
            {
                "domain": domain,
                "is_competitor": c.get("is_competitor", False),
                "confidence": c.get("confidence", 0.0),
                "frequency": ev["frequency"],
                "found_via_listicle": ev["mined"],
                "reason": c.get("reason", ""),
                "matched_queries": ", ".join(sorted(ev["sources"])) if ev["sources"] else "",
            }
        )

    confirmed = [
        r
        for r in rows
        if r["is_competitor"] is True
        and not is_same_brand_or_domain(r["domain"], site_url, company_name)
    ]
    confirmed.sort(key=lambda r: (r["frequency"], r["confidence"]), reverse=True)

    logger.info(
        "Competitor discovery for %s: %d confirmed competitors (of %d candidates)",
        site_url,
        len(confirmed),
        len(rows),
    )

    return {
        "business_summary": summary,
        "queries": query_sets,
        "competitors": confirmed,
        "all_candidates": rows,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def select_display_competitors(
    competitors: List[dict],
    min_count: int = MIN_DISPLAY_COMPETITORS,
    max_count: int = MAX_DISPLAY_COMPETITORS,
    self_url: str = "",
    company_name: str = "",
) -> List[dict]:
    """Prioritize confidently-direct competitors, capped to [min_count, max_count].

    `competitors` must already be is_competitor==True only (i.e.
    discover_competitors()'s own "competitors" output). Low-confidence
    (likely-not-actually-direct) entries only pad the list up to min_count —
    they never get pulled in just to fill unused room up to max_count.

    Deliberately does NOT reach into classify_batch's rejected
    (is_competitor=False) pool to hit min_count — tried that and it surfaced
    things like a media publication and a solar-energy nonprofit as
    "competitors" just to fill the quota for thin markets. Never fabricates —
    if fewer than min_count were confirmed at all (by the classifier, at any
    confidence), returns however many actually were.
    """
    if self_url or company_name:
        competitors = [
            c
            for c in competitors
            if not is_same_brand_or_domain(c.get("domain", ""), self_url, company_name)
        ]

    high = [c for c in competitors if c["confidence"] >= DIRECT_CONFIDENCE_THRESHOLD]
    if len(high) >= min_count:
        return high[:max_count]

    rest = [c for c in competitors if c["confidence"] < DIRECT_CONFIDENCE_THRESHOLD]
    return (high + rest)[:min_count]
