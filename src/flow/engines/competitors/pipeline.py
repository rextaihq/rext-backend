"""Orchestrates SERP-based competitor discovery: seed keywords -> SERP search -> scoring/tiering."""
import logging
from datetime import datetime, timezone
from typing import Any, Dict

from src.flow.engines.competitors.keyword_volume import select_top_keywords_by_volume
from src.flow.engines.competitors.scoring import fetch_domain_snippet, score_domain
from src.flow.engines.competitors.seed_keywords import generate_seed_keywords
from src.flow.engines.competitors.serp_discovery import aggregate_domains, run_serp_search

logger = logging.getLogger(__name__)


async def discover_competitors(
    *,
    business_content: str,
    own_domain: str,
    location_name: str = "United States",
    language_code: str = "en",
    max_keywords: int = 8,
    top_n_domains: int = 10,
) -> Dict[str, Any]:
    """Pure orchestration function — no DB/SSE concerns, safe to unit test in isolation."""
    seed_data = await generate_seed_keywords(business_content)

    all_keywords = [seed_data.primary_keyword] + list(seed_data.secondary_keywords or [])
    all_keywords = [k for k in all_keywords if k]
    top_keywords = await select_top_keywords_by_volume(
        all_keywords, top_n=max_keywords, location_name=location_name, language_code=language_code
    )

    keyword_results: Dict[str, list] = {}
    for kw in top_keywords:
        keyword_results[kw] = await run_serp_search(kw, location_name, language_code)

    domain_data = aggregate_domains(keyword_results, own_domain)
    ranked_candidates = sorted(
        domain_data.items(), key=lambda kv: kv[1]["serp_appearances"], reverse=True
    )[:top_n_domains]
    max_serp_appearances = max((e["serp_appearances"] for _, e in ranked_candidates), default=1)

    scored = []
    for cand_domain, entry in ranked_candidates:
        snippet = await fetch_domain_snippet(cand_domain)
        result = await score_domain(
            cand_domain, entry, snippet,
            seed_data.business_summary, seed_data.audience, max_serp_appearances,
        )
        scored.append(result)

    scored.sort(key=lambda r: r["competitor_score"], reverse=True)
    business_competitors = [r for r in scored if r["competitor_type"] == "business_competitor"]
    content_competitors = [r for r in scored if r["competitor_type"] == "content_competitor"]
    suppliers_excluded = [r for r in scored if r["competitor_type"] == "supplier_or_manufacturer"]

    logger.info(
        "Competitor discovery for %s: %d business, %d content, %d supplier (of %d scored)",
        own_domain, len(business_competitors), len(content_competitors),
        len(suppliers_excluded), len(scored),
    )

    return {
        "seed_keywords": seed_data.model_dump(),
        "business_competitors": business_competitors,
        "content_competitors": content_competitors,
        "suppliers_excluded": suppliers_excluded,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "location_name": location_name,
    }


_TIER_PRIORITY = ["Direct competitor", "Strong competitor", "Indirect competitor"]


def select_top_competitors(analysis: Dict[str, Any] | None, min_count: int = 3, max_count: int = 5) -> list:
    """Direct -> Strong -> Indirect fallback selection, capped at max_count."""
    if not analysis:
        return []
    business_competitors = analysis.get("business_competitors") or []

    top: list = []
    for tier in _TIER_PRIORITY:
        if len(top) >= max_count:
            break
        for comp in business_competitors:
            if comp.get("tier") == tier and comp not in top:
                top.append(comp)
                if len(top) >= max_count:
                    break

    return top[:max_count]
