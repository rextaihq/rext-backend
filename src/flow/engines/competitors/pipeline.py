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
from typing import Any, Dict, List, Optional

from src.flow.engines.competitors.aggregation import aggregate_candidates
from src.flow.engines.competitors.classification import classify_all
from src.flow.engines.competitors.constants import (
    DIRECT_CONFIDENCE_THRESHOLD,
    MAX_DISPLAY_COMPETITORS,
    MAX_QUERIES,
    MIN_DISPLAY_COMPETITORS,
)
from src.flow.engines.competitors.listicle import mine_all_listicles
from src.flow.engines.competitors.llm_client import generate_queries, summarize_business
from src.flow.engines.competitors.scraping import scrape_site
from src.flow.engines.competitors.serp import configuration_error, run_all_searches

logger = logging.getLogger(__name__)


async def discover_competitors(
    site_url: str,
    pages: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Faithful port of the notebook's find_competitors(site_url)."""
    if error := configuration_error():
        logger.warning("%s", error)
        return {
            "business_summary": {},
            "queries": {},
            "competitors": [],
            "all_candidates": [],
            "status": "unavailable",
            "reason": error,
        }

    pages = pages if pages is not None else await scrape_site(site_url)
    if not pages:
        return {
            "business_summary": {},
            "queries": {},
            "competitors": [],
            "all_candidates": [],
            "status": "unavailable",
            "reason": "No accessible site content was available for competitor analysis.",
        }
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

    serp_results = await run_all_searches(queries)
    logger.info("Competitor discovery: got %d raw SERP results", len(serp_results))

    mined_domains = await mine_all_listicles(serp_results)
    logger.info("Competitor discovery: mined %d domains from listicles", len(mined_domains))

    candidates = aggregate_candidates(site_url, serp_results, mined_domains)
    logger.info(
        "Competitor discovery: %d unique candidates going to classification", len(candidates)
    )

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

    confirmed = [r for r in rows if r["is_competitor"] is True]
    # Confidence first: sorting on SERP frequency put big platforms that rank
    # for every query ahead of the actual direct competitors.
    confirmed.sort(key=lambda r: (r["confidence"], r["frequency"]), reverse=True)

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
        "status": "complete",
    }


def select_display_competitors(
    competitors: List[dict],
    min_count: int = MIN_DISPLAY_COMPETITORS,
    max_count: int = MAX_DISPLAY_COMPETITORS,
) -> List[dict]:
    """Confidently-direct competitors only, capped to max_count.

    `competitors` must already be is_competitor==True only (i.e.
    discover_competitors()'s own "competitors" output). Low-confidence
    (likely-not-actually-direct) entries are never shown, not even to reach
    min_count — padding with them is what surfaced wrong competitors. A thin
    market returns a short list. `min_count` is kept for caller compatibility.

    Deliberately does NOT reach into classify_batch's rejected
    (is_competitor=False) pool to hit min_count — tried that and it surfaced
    things like a media publication and a solar-energy nonprofit as
    "competitors" just to fill the quota for thin markets. Never fabricates —
    if fewer than min_count were confirmed at all (by the classifier, at any
    confidence), returns however many actually were.
    """
    high = [c for c in competitors if c["confidence"] >= DIRECT_CONFIDENCE_THRESHOLD]
    return high[:max_count]
