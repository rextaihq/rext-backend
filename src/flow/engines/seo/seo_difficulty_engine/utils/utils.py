import math
import statistics
from collections import Counter
from typing import List, Dict, Any
from datetime import datetime, timezone

ugc_keywords = ["reddit.com", "quora.com", "stackexchange.com", "stackoverflow.com"]


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

INTENT_WEIGHTS = {
    "informational": {"link": 0.50, "serp": 0.30, "content": 0.20},
    "commercial": {"link": 0.55, "serp": 0.30, "content": 0.15},
    "transactional": {"link": 0.60, "serp": 0.30, "content": 0.10},
    "navigational": {"link": 0.70, "serp": 0.25, "content": 0.05},
}


def classify_domain_type(domain: str) -> str:
    """Classify a domain into a category based on its suffix or name.

    Categories: gov, edu, publisher, brand, ugc, other.

    Args:
        domain: Domain name to classify.

    Returns:
        str: Domain category.
    """
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

    
    if any(u in domain for u in ugc_keywords):
        return "ugc"

    return "other"



def clamp(val, min_v=0, max_v=1):
    """Clamp a value between a minimum and maximum.

    Args:
        val: The value to clamp.
        min_v: Minimum value (default 0).
        max_v: Maximum value (default 1).

    Returns:
        float: The clamped value.
    """
    return max(min(val, max_v), min_v)


def normalize_rd(rd, cap=1000):
    """Normalize referring domains count using log scale.

    Args:
        rd: Referring domains count.
        cap: Maximum value for normalization (default 1000).

    Returns:
        float: Normalized score between 0 and 1.
    """
    return clamp(math.log1p(rd) / math.log1p(cap))

def dofollow_proxy(domain_type: str) -> float:
    """Get link value multiplier based on domain type.

    Args:
        domain_type: Type of domain (gov, edu, publisher, etc.).

    Returns:
        float: Multiplier value between 0.4 and 0.95.
    """
    mapping = {"gov": 0.95, "edu": 0.90, "publisher": 0.85, "brand": 0.75, "ugc": 0.4, "other": 0.55}
    return mapping.get(domain_type, 0.5)

def anchor_proxy(keyword: str, title: str) -> float:
    """Calculate anchor text relevance score.

    Args:
        keyword: Target keyword.
        title: Page title (used as proxy for anchor text).

    Returns:
        float: Score indicating relevance (0.1 to 0.7).
    """
    keyword = keyword.lower()
    title = title.lower()
    if title.startswith(keyword):
        return 0.7
    elif keyword in title:
        return 0.4
    return 0.1

def is_homepage(url: str) -> bool:
    """Check if a URL is a homepage.

    Args:
        url: The URL to check.

    Returns:
        bool: True if homepage, False otherwise.
    """
    try:
        parts = url.rstrip("/").split("/")
        return url.rstrip("/").endswith(parts[2]) or url.rstrip("/") == parts[0] + "://" + parts[2]
    except IndexError:
        return False

# ------------------------
# Link strength calculation
# ------------------------
def url_link_strength(keyword: str, comp: Dict[str, Any], serp_entry: Dict[str, Any]) -> float:
    """Compute link strength score for a single competitor.

    Combines referring domains, domain authority, and anchor relevance.
    Applies penalties for non-exact anchors and boosts for featured snippets.

    Args:
        keyword: Target keyword.
        comp: Competitor data dictionary.
        serp_entry: SERP entry dictionary.

    Returns:
        float: Link strength score between 0 and 1.
    """

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
    """Calculate median link strength across all competitors.

    Args:
        keyword: Target keyword.
        competitors: List of competitor data.
        serp_normalized: List of normalized SERP results.

    Returns:
        float: Median link strength score.
    """
    domain_map = {entry["domain"]: entry for entry in serp_normalized}
    scores = [
        url_link_strength(keyword, comp, domain_map.get(comp["domain"], {}))
        for comp in competitors
    ]
    return statistics.median(scores)

def serp_lock_penalty(competitors: List[Dict[str, Any]]) -> float:
    """Calculate penalty for SERP dominance by few domains.

    Args:
        competitors: List of competitor data.

    Returns:
        float: Penalty score (0.0 to 0.15).
    """
    domains = [c["domain"] for c in competitors]
    max_repeat = Counter(domains).most_common(1)[0][1]
    if max_repeat >= 3:
        return 0.15
    elif max_repeat == 2:
        return 0.07
    return 0.0

def homepage_penalty(competitors: List[Dict[str, Any]]) -> float:
    """Calculate penalty for high number of homepages in SERP.

    Args:
        competitors: List of competitor data.

    Returns:
        float: Penalty score (0.0 to 0.10).
    """
    homepage_count = sum(1 for c in competitors if c.get("has_sitelinks") or is_homepage(c.get("domain", "")))
    share = homepage_count / len(competitors)
    if share > 0.6:
        return 0.10
    elif share > 0.4:
        return 0.05
    return 0.0

def brand_share(competitors: List[Dict[str, Any]]) -> float:
    """Calculate share of brand domains in competitors.

    Args:
        competitors: List of competitor data.

    Returns:
        float: Fraction of competitors that are brands (0 to 1).
    """
    # Fraction of top competitors that are brand domains
    brands = [c for c in competitors if classify_domain_type(c["domain"]) == "brand"]
    return len(brands) / max(len(competitors), 1)


def normalize_freshness(date_str):
    """Normalize content freshness based on date.

    Args:
        date_str: Date string (ISO format).

    Returns:
        float: Freshness score (1.0 for very recent, decaying to 0.0).
    """
    if not date_str:
        return 0.3  # unknown freshness

    try:
        dt = datetime.fromisoformat(date_str)
        days = (datetime.now() - dt).days

        if days <= 30:
            return 1.0
        elif days <= 180:
            return 0.85
        elif days <= 365:
            return 0.4
        else:
            return 0.0
        
    except:
        return 0.3