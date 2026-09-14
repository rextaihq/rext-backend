"""Candidate-domain aggregation, ported from the reference Colab notebook.

One deviation: candidates are also excluded via PLATFORM_BLOCKLIST_DOMAINS
(major website-building/CMS/e-commerce platforms like wordpress.com) — see
that constant's docstring for why.
"""

from collections import defaultdict
from typing import List

from src.flow.engines.competitors.constants import (
    BLOCKLIST_DOMAINS,
    LISTICLE_DOMAINS,
    MAX_CANDIDATES_TO_CLASSIFY,
    PLATFORM_BLOCKLIST_DOMAINS,
)
from src.flow.engines.competitors.domain_utils import is_same_brand_or_domain, normalize_domain

_EXCLUDED_DOMAINS = BLOCKLIST_DOMAINS | PLATFORM_BLOCKLIST_DOMAINS


def aggregate_candidates(
    self_url: str,
    serp_results: List[dict],
    mined_domains: list,
    company_name: str = "",
) -> dict:
    evidence = defaultdict(
        lambda: {"frequency": 0, "sources": set(), "mined": False, "title": "", "snippet": ""}
    )

    for r in serp_results:
        d = normalize_domain(r["link"])
        if (
            not d
            or is_same_brand_or_domain(d, self_url, company_name)
            or d in _EXCLUDED_DOMAINS
            or d in LISTICLE_DOMAINS
        ):
            continue
        evidence[d]["frequency"] += 1
        evidence[d]["sources"].add(r["query"])
        if not evidence[d]["title"] and r.get("title"):
            evidence[d]["title"] = r["title"]
        if not evidence[d]["snippet"] and r.get("snippet"):
            evidence[d]["snippet"] = r["snippet"]

    for d in mined_domains:
        d = normalize_domain(str(d).lower().strip())
        if (
            not d
            or is_same_brand_or_domain(d, self_url, company_name)
            or d in _EXCLUDED_DOMAINS
        ):
            continue
        evidence[d]["frequency"] += 1
        evidence[d]["mined"] = True

    ranked = sorted(evidence.items(), key=lambda kv: kv[1]["frequency"], reverse=True)
    return dict(ranked[:MAX_CANDIDATES_TO_CLASSIFY])

