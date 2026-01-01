import math
import statistics
from collections import Counter
from typing import List, Dict, Any

# ------------------------
# Domain authority mapping
# ------------------------
DOMAIN_AUTHORITY_MAP = {
    "gov": 100,
    "edu": 90,
    "publisher": 80,
    "brand": 70,
    "ugc": 55,
    "other": 30
}

def classify_domain_type(domain: str) -> str:
    domain = domain.lower()
    if domain.endswith(".gov") or ".gov." in domain:
        return "gov"
    if domain.endswith(".edu") or ".edu." in domain:
        return "edu"

    publisher_keywords = [
        "wikipedia", "forbes", "nytimes", "bbc", "cnn",
        "techcrunch", "medium", "investopedia", "coursera",
        "datacamp", "geeksforgeeks", "ibm", "sap", "mit"
    ]
    if any(p in domain for p in publisher_keywords):
        return "publisher"

    brand_keywords = [
        "google", "microsoft", "amazon", "ibm", "sap", "oracle"
    ]
    if any(b in domain for b in brand_keywords):
        return "brand"

    ugc_keywords = ["reddit", "quora", "stackexchange", "stackoverflow"]
    if any(u in domain for u in ugc_keywords):
        return "ugc"

    return "other"

def clamp(val, min_v=0, max_v=1):
    return max(min(val, max_v), min_v)

def normalize_rd(rd, cap=1000):
    """Referring domains proxy log-scale normalization with freshness boost"""
    return clamp(math.log1p(rd) / math.log1p(cap))

def dofollow_proxy(domain_type: str) -> float:
    mapping = {"gov": 0.95, "edu": 0.90, "publisher": 0.85, "brand": 0.75, "ugc": 0.4, "other": 0.55}
    return mapping.get(domain_type, 0.5)

def anchor_proxy(keyword: str, title: str) -> float:
    keyword = keyword.lower()
    title = title.lower()
    if title.startswith(keyword):
        return 0.7
    elif keyword in title:
        return 0.4
    return 0.1

def is_homepage(url: str) -> bool:
    try:
        parts = url.rstrip("/").split("/")
        return url.rstrip("/").endswith(parts[2]) or url.rstrip("/") == parts[0] + "://" + parts[2]
    except IndexError:
        return False

# ------------------------
# Link strength calculation
# ------------------------
def url_link_strength(keyword: str, comp: Dict[str, Any], serp_entry: Dict[str, Any]) -> float:
    """Compute link strength for one competitor with all improvements"""

    # RD score + freshness boost
    rd_proxy = comp.get("total_occurrences", 1) * 10
    freshness = comp.get("freshness", {}).get("recent", 0)
    rd_score = normalize_rd(rd_proxy) + (0.05 * freshness)  # small freshness boost

    # Domain authority
    domain_type = classify_domain_type(comp["domain"])
    authority = DOMAIN_AUTHORITY_MAP.get(domain_type, 30) / 100
    dofollow = dofollow_proxy(domain_type)

    # Anchor relevance using title
    title = serp_entry.get("title", comp["domain"])
    exact_anchor_pct = anchor_proxy(keyword, title)

    # Base link strength
    base = (
        0.45 * rd_score +
        0.20 * dofollow +
        0.20 * authority
    )

    # Penalize if anchor not exact
    if exact_anchor_pct > 0.6:
        base -= 0.15
    elif exact_anchor_pct > 0.4:
        base -= 0.08

    # Boost for featured snippet
    if comp.get("featured_snippet", False):
        base += 0.05

    return clamp(base)

def median_link_strength(keyword: str, competitors: List[Dict[str, Any]], serp_normalized: List[Dict[str, Any]]) -> float:
    """Median link strength across competitors"""
    domain_map = {entry["domain"]: entry for entry in serp_normalized}
    scores = [
        url_link_strength(keyword, comp, domain_map.get(comp["domain"], {}))
        for comp in competitors
    ]
    return statistics.median(scores)

def serp_lock_penalty(competitors: List[Dict[str, Any]]) -> float:
    domains = [c["domain"] for c in competitors]
    max_repeat = Counter(domains).most_common(1)[0][1]
    if max_repeat >= 3:
        return 0.15
    elif max_repeat == 2:
        return 0.07
    return 0.0

def homepage_penalty(competitors: List[Dict[str, Any]]) -> float:
    homepage_count = sum(1 for c in competitors if c.get("has_sitelinks") or is_homepage(c.get("domain", "")))
    share = homepage_count / len(competitors)
    if share > 0.6:
        return 0.10
    elif share > 0.4:
        return 0.05
    return 0.0

def brand_share(competitors: List[Dict[str, Any]]) -> float:
    # Fraction of top competitors that are brand domains
    brands = [c for c in competitors if classify_domain_type(c["domain"]) == "brand"]
    return len(brands) / max(len(competitors), 1)

