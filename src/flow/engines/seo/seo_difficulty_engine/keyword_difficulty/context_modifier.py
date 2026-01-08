from collections import Counter
from src.flow.states.wrext import SERPNORMALIZED, Competitor
from src.flow.engines.seo.seo_difficulty_engine.utils.utils import classify_domain_type


def context_modifier(competitors: list[Competitor], serp_normalized: SERPNORMALIZED, keyword_intent: str) -> float:
    modifier = 0.0

    # --------------------
    # Reduce KD (-)
    # --------------------
    # 1️⃣moderate Many new or weak domains (domain_stats proxy)

    domains = serp_normalized["domains"]  # list of domains from SERP
    ugc_domains = sum(1 for d in domains if classify_domain_type(d) in ["ugc"])

    if ugc_domains >= len(domains) * 0.3:
        modifier -= 4.0

    weak_domains = sum(1 for d in domains if classify_domain_type(d) in ["other"])


    if weak_domains >= len(domains) * 0.3:
        modifier -= 2.0


    # --------------------
    # Increase KD (+)
    # --------------------
    # 1️⃣ Strong brand dominance
    
    brands = {"brand", "publisher", "gov", "edu"}
    brand_count = sum(1 for domain in serp_normalized["domains"] if classify_domain_type(domain) in brands)
    # brand_count = sum(1 for c in competitors if wrext_normalized["domain_stats"].get(c["domain"], {}).get("type") in brands)

    if brand_count >= len(competitors) * 0.8:
        modifier += 10.0
    elif brand_count >= len(competitors) * 0.5:
        modifier += 4.0
    elif brand_count >= len(competitors) * 0.3:
        modifier += 2.0


    # Forums dominance (>30% of top competitors are UGC)
    # forums_count = sum(1 for c in competitors if c.get("domain_type") == "ugc")
    # forums_dominance = forums_count >= len(competitors) * 0.3
    # if forums_dominance:
    #     score += 3




    # all_domains = serp_normalized.get("domains", [])

    # forums_count = sum(1 for c in all_domains if any(u in c for u in ugc_keywords))
    # forums_dominance = forums_count >= len(all_domains) * 0.3
    # if forums_dominance:
    #     score += 3

    # # 2️⃣ SERP dominated by forums / UGC
    # ugc_count = sum(1 for c in competitors if wrext_normalized["domain_stats"].get(c["domain"], {}).get("type") == "ugc")
    # if ugc_count >= len(competitors) * 0.3:
    #     modifier -= 2.0

    # 3️⃣ Poor intent alignment
    
    intent_mismatches = sum(
        1 for c in competitors
        if keyword_intent not in c.get("intent_distribution", {}) or c["intent_distribution"].get(keyword_intent, 0)/max(1,sum(c.get("intent_distribution", {}).values())) < 0.3
    )
    if intent_mismatches >= len(competitors) * 0.4:
        modifier -= 4.0




    '''
    # 2️⃣ Homepage rankings dominate
    homepage_count = sum(1 for c in competitors if c.get("has_sitelinks", False))
    if homepage_count >= len(competitors) * 0.6:
        modifier += 2.0
    '''
    # Clamp modifier to ±5
    return max(min(modifier, 5), -5)
