# from .base import DifficultyComponent
# from src.flow.engines.seo.seo_difficulty_engine.keyword_difficulty.link_difficulty import competitor_link_kd

# class LinkDifficulty(DifficultyComponent):
#     name = "link"

#     def score(self, ctx):
#         return competitor_link_kd(
#             keyword=ctx.keyword,
#             comp=ctx.competitor,
#             serp_entry=ctx.serp_entry,
#             normalized_results=ctx.serp_results,
#             competitors=ctx.competitors,
#         )


import math
from .base import DifficultyComponent
from ...utils.math import clamp
from ...utils.domains import classify_domain_type, DOMAIN_AUTHORITY_MAP
from ...utils.freshness import normalize_freshness

def normalize_rd(rd, cap=1000):
    return clamp(math.log1p(rd) / math.log1p(cap))

def dofollow_proxy(domain_type: str) -> float:
    mapping = {
        "gov": 0.95, "edu": 0.90, "publisher": 0.85,
        "brand": 0.75, "ugc": 0.4, "other": 0.55
    }
    return mapping.get(domain_type, 0.5)

def anchor_proxy(keyword: str, title: str, url: str) -> float:
    keyword = keyword.lower()
    title = title.lower()

    score = 0.1
    if title.startswith(keyword):
        score = 0.7
    elif keyword in title:
        score = 0.6

    if url and keyword in url:
        score += 0.3

    return score

def is_homepage(url: str) -> bool:
    try:
        parts = url.rstrip("/").split("/")
        return url.rstrip("/").endswith(parts[2])
    except Exception:
        return False

def url_link_strength(keyword, comp, serp_entry, normalized_results):
    rd_proxy = comp.get("total_occurrences", 1) * 10
    freshness = normalize_freshness(serp_entry.get("date"))
    rd_score = normalize_rd(rd_proxy) + (0.05 * freshness)

    domain_type = classify_domain_type(comp["domain"])
    authority = DOMAIN_AUTHORITY_MAP.get(domain_type, 30) / 100
    dofollow = dofollow_proxy(domain_type)

    title = serp_entry.get("title", comp["domain"])
    url = serp_entry.get("url")
    anchor_score = anchor_proxy(keyword, title, url)

    base = (
        0.45 * rd_score +
        0.20 * dofollow +
        0.20 * authority
    )

    if anchor_score > 0.6:
        base += 0.15

    if comp.get("featured_snippet"):
        base += 0.05

    return clamp(base)

class LinkDifficulty(DifficultyComponent):
    name = "link"

    def score(self, ctx):
        base = url_link_strength(
            ctx.keyword,
            ctx.competitor,
            ctx.serp_entry,
            ctx.serp_results
        )

        brands = {"publisher", "gov", "edu"}
        authority_domains = sum(
            1 for c in ctx.competitors
            if classify_domain_type(c["domain"]) in brands
        )

        serp_lock = 0.2 if authority_domains >= 4 else 0.05 if authority_domains >= 2 else 0
        brand_boost = 0.10 if classify_domain_type(ctx.competitor["domain"]) == "brand" else 0.0
        homepage_boost = 0.10 if is_homepage(ctx.serp_entry.get("url", "")) else 0.0

        return clamp(base + serp_lock + brand_boost + homepage_boost)
