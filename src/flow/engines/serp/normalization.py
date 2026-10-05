import logging
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Dict, List
from urllib.parse import urlparse

from dateutil import parser

from src.flow.states.rext import REXT, NormalizedOrganicResult

logger = logging.getLogger(__name__)


def has_organic_results(state: REXT) -> bool:
    """Whether the normalised SERP holds any organic result.

    Without one there is nothing to build an article from: the SERP subgraph
    stops before the competitor analysis, the main graph ends the run at
    no_serp_data before any credit is charged, and keyword_recommendation
    opens no gate. One definition, so those three cannot disagree.
    """
    return bool((state.get("serp_normalized") or {}).get("normalize_results"))


def normalize_serp_results(state: REXT, config, *, runtime) -> Dict[str, Any]:
    """
    Normalize raw SERP results into a structured format for further analysis.

    Args:
        state (REXT): The current state containing the raw serp_result.

    Returns:
        Dict[str, Any]: A dictionary containing the normalized SERP data.
    """
    # Access the store from runtime
    _store = runtime.store
    logger.info("Starting SERP normalization")
    serp_payload = state.get("serp_payload", {})
    query = serp_payload.get("query", "")
    serp_result = state.get("serp_result", {})

    organic = serp_result.get("organic_results", [])
    related_searches = serp_result.get("related_searches", [])
    people_ask = serp_result.get("people_ask", [])
    search_params = serp_result.get("search_params", {})

    engine = search_params.get("se", "google")
    logger.debug(f"Normalizing results for engine: {engine}, query: '{query}'")

    normalized_results: List[NormalizedOrganicResult] = []
    domains: List[str] = []
    year_counter = Counter()

    # Normalize Organic Results
    for item in organic:
        url = item.get("link", "")
        domain = urlparse(url).netloc.replace("www.", "") if url else ""

        year = None

        # ---- 1️⃣ timestamp (best signal) ----
        date = item.get("timestamp")
        if date:
            try:
                dt = parser.parse(date)
                year = str(dt.year)
            except Exception:
                pass

        # ---- 3️⃣ classify ----
        if year and year.isdigit():
            year_counter[year] += 1
        else:
            year_counter["older"] += 1

        # has_sitelinks = bool(item.get("sitelinks"))

        normalized_results.append(
            {
                "position": item.get("position"),
                "title": item.get("title"),
                "url": url,
                "snippet": item.get("snippet"),
                "domain": domain,
                "date": date,
                # "has_sitelinks": has_sitelinks
            }
        )

        if domain:
            domains.append(domain)

    unique_domains = list(set(domains))
    logger.debug(
        f"Normalized {len(normalized_results)} organic results across {len(unique_domains)} unique domains"
    )

    # Freshness Analysis
    current_year = datetime.now(timezone.utc).year
    freshness = {
        "recent": year_counter.get(str(current_year), 0),
        "older": sum(year_counter.values()) - year_counter.get(str(current_year), 0),
    }

    # SERP Features
    features = {
        "people_also_ask": bool(people_ask),
        # True or False from the SERP, None when it could not be read.
        "ai_overview": serp_result.get("ai_overview"),
        # "sitelinks": any(r["has_sitelinks"] for r in normalized_results),
        # "wikipedia": any("wikipedia.org" in d for d in domains)
    }

    # Domain Stats
    domain_stats = {
        "unique_domains": len(unique_domains),
        "top_domains": [d for d, _ in Counter(domains).most_common(5)],
    }

    # Final Normalized State
    serp_normalized = {
        "query": query,
        "engine": engine,
        "normalize_results": normalized_results,
        "related_topics": related_searches,
        "questions": [q.get("question") for q in people_ask],
        "stats": {"organic_count": len(normalized_results)},
        "domains": unique_domains,
        "domain_stats": domain_stats,
        "freshness": freshness,
        "features": features,
    }

    logger.info("Completed SERP normalization")
    return {"serp_normalized": serp_normalized}
