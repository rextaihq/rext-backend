import math
import statistics
from urllib.parse import urlparse
from collections import Counter
from typing import List, Dict, Any
from src.flow.states.rext import Competitor, NormalizedOrganicResult
from datetime import datetime, timezone
from src.flow.engines.seo.seo_difficulty_engine.utils.utils import DOMAIN_AUTHORITY_MAP, normalize_freshness, classify_domain_type, clamp

def normalize_rd(rd, cap=1000):
    """Referring domains proxy log-scale normalization with freshness boost"""
    return clamp(math.log1p(rd)  /math.log1p(cap))

def dofollow_proxy(domain_type: str) -> float:
    mapping = {"gov": 0.95, "edu": 0.90, "publisher": 0.85, "brand": 0.75, "ugc": 0.4, "other": 0.55}
    
    return mapping.get(domain_type, 0.5)

def anchor_proxy(keyword: str, title: str, url: str) -> float:
    anchor_score = 0.0
    keyword = keyword.lower()
    title = title.lower()
    if title.startswith(keyword):
        anchor_score += 0.7
    elif keyword in title:
        anchor_score += 0.6
    else:
        anchor_score += 0.1

    if keyword in url:
        anchor_score += 0.3

    return anchor_score


def is_homepage(url: str) -> bool:
    try:
        parts = url.rstrip("/").split("/")
        return url.rstrip("/").endswith(parts[2]) or url.rstrip("/") == parts[0] + "://" + parts[2]
    except IndexError:
        return False

# -----------------------
# Link strength calculation
# ------------------------

def url_link_strength(keyword: str, comp: Competitor, serp_entry: NormalizedOrganicResult, normalized_result: List[NormalizedOrganicResult]) -> float:
    """Compute link strength for one competitor with all improvements"""

    """
    total_occurrences = 5
    rd_proxy = 5 * 10 = 50
    normalize_rd(50) ~ 0.39   # meaningful score

    """
    
    
    # RD score + freshness boost
    rd_proxy = comp.get("total_occurrences", 1) * 10

    freshness = normalize_freshness(serp_entry.get("date"))
    
    rd_score = normalize_rd(rd_proxy) + (0.05 * freshness) 

    # Domain authority
    domain_type = classify_domain_type(comp["domain"])
    authority = DOMAIN_AUTHORITY_MAP.get(domain_type, 30) / 100
    dofollow = dofollow_proxy(domain_type)

    # Anchor relevance using title
    title = serp_entry.get("title", comp["domain"])
    url = serp_entry.get("url", None)
    exact_anchor_pct = anchor_proxy(keyword, title, url)

    # Base link strength
    base = (
        0.45 * rd_score +
        0.20 * dofollow +
        0.20 * authority
    )

    if exact_anchor_pct > 0.6:
        base += 0.15
    elif exact_anchor_pct >= 0.6:
        base += 0.10

    # Boost for featured snippet
    if comp.get("featured_snippet", False):
        base += 0.05

    return clamp(base)
'''
def median_link_strength(keyword: str, competitors: Competitor, serp_normalized: NormalizedOrganicResult) -> float:
    """Median link strength across competitors"""
    domain_map = {entry["domain"]: entry for entry in serp_normalized}

    scores = [
        url_link_strength(keyword, comp, domain_map.get(comp["domain"], {}),serp_normalized)
        for comp in competitors
    ]

    return statistics.median(scores)
'''
"""
def serp_lock_penalty(competitors: Competitor) -> float:
    domains = [c["domain"] for c in competitors]
    max_repeat = Counter(domains).most_common(1)[0][1]
    if max_repeat >= 3:
        return 0.15
    elif max_repeat == 2:
        return 0.07
    return 0.0

"""

def homepage_score(comp: Competitor) -> float:
    homepage_count = is_homepage(comp.get("domain", ""))
    
    if homepage_count:
        return 0.10
    
    return 0.0
'''

def homepage_score(competitors: Competitor) -> float:
    homepage_count = sum(1 for c in competitors if c.get("has_sitelinks") or is_homepage(c.get("domain", "")))
    share = homepage_count / len(competitors)
    if share > 0.6:
        return 0.10
    elif share > 0.4:
        return 0.05
    return 0.0
'''
"""
def brand_share(competitors: Competitor) -> float:
    # Fraction of top competitors that are brand domains
    brands = [c for c in competitors if classify_domain_type(c["domain"]) == "brand"]
    return len(brands) / max(len(competitors), 1)
"""
# ------------------------
# Main link difficulty function
# ------------------------
'''
def link_difficulty_score(keyword: str, competitors: Competitor, serp_normalized: NormalizedOrganicResult) -> Dict[str, Any]:
    link_strength = median_link_strength(keyword, competitors, serp_normalized)
    serp_repeted_score = serp_lock_penalty(competitors) 
    # penalties = serp_lock_penalty(competitors) + homepage_penalty(competitors)
    Branded = clamp(brand_share(competitors))

    final = clamp(link_strength + serp_repeted_score + (Branded * 0.10))
    KD_score = round(final * 100, 2)

    return {
        "link_difficulty": KD_score,
        "details": {
            "median_link_strength": round(link_strength, 3),
            "serp_repeted_score": serp_repeted_score,
            # "homepage_penalty": homepage_penalty(competitors),
            "brand_share": round(Branded, 2)
        }
    }
'''




def competitor_link_kd(
    keyword: str,
    comp: Competitor,
    serp_entry: NormalizedOrganicResult,
    normalized_results: List[NormalizedOrganicResult],
    competitors: List[Competitor]
) -> float:
    """
    Full Link KD for ONE competitor (New Approach)
    """

    # Base link strength (unchanged logic)
    base_strength = url_link_strength(
        keyword=keyword,
        comp=comp,
        serp_entry=serp_entry,
        normalized_result=normalized_results
    )

    # -------- Per-competitor SERP lock --------
    brands = {"publisher", "gov", "edu"}
    domains = [c["domain"] for c in competitors]
    authority_domains = sum(1 for d in domains if classify_domain_type(d) in brands)
    
    # repeat_count = domains.count(comp["domain"])

    serp_lock = 0.0
    if authority_domains >= 4:
        serp_lock = 0.20

    elif authority_domains >= 2:
        serp_lock = 0.5

    # -------- Per-competitor brand pressure --------
    brand_boost = 0.10 if classify_domain_type(comp["domain"]) == "brand" else 0.0
    homepage_scoring = homepage_score(comp)

    # Final per-competitor link KD
    return clamp(base_strength + serp_lock + brand_boost + homepage_scoring)

'''
def link_difficulty_score(
    keyword: str,
    competitors: List[Competitor],
    serp_normalized: List[NormalizedOrganicResult]
) -> Dict[str, Any]:
        

        domain_map = {r["domain"]: r for r in serp_normalized}

        competitor_link_kds = [
            competitor_link_kd(
                keyword=keyword,
                comp=comp,
                serp_entry=domain_map.get(comp["domain"], {}),
                normalized_results=serp_normalized,
                competitors=competitors
            )
            for comp in competitors
        ]

        final_link_kd = statistics.median(competitor_link_kds)
        KD_score = round(final_link_kd * 100, 2)

        return {
            "link_difficulty": KD_score,
            "details": {
                "median_competitor_link_kd": round(final_link_kd, 3),
                "competitor_count": len(competitor_link_kds)
            }
        }

        '''