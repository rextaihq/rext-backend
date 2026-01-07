# from typing import Dict
# from src.flow.states.wrext import WREXT
# from src.flow.states.seo_state import SEORESULT


# def keyword_difficulty_node(state: WREXT) -> Dict[str, SEORESULT]:
#     competitors = state.get("competitors", [])
#     serp = state.get("serp_normalized", {})
#     scrape_context = state.get("scrape_context", {}) or {}

#     keyword = (state.get("serp_payload") or {}).get("query", "").lower()
#     intent = (serp.get("intent") or {}).get("primary_intent")

#     normalized_results = serp.get("normalize_results", [])

#     # 1. AUTHORITY PRESSURE (0–25)
#     dominance = 0
#     unique_domains = set()

#     for c in competitors:
#         if c.get("domain"):
#             unique_domains.add(c["domain"])

#         for pos in c.get("top_positions", []):
#             if pos <= 2:
#                 dominance += 2
#             elif pos <= 4:
#                 dominance += 1
#         total_occurrences_sum = sum(c.get("total_occurrences", 0) for c in competitors)
#         authority_pressure = min(6, total_occurrences_sum)

#     # Featured snippet ownership
#     link_score = 0
#     fs_ratio = sum(1 for c in competitors if c.get("featured_snippet")) / max(1, len(competitors))
#     if fs_ratio >= 0.3:
#         link_score += 8
#     elif fs_ratio >= 0.1:
#         link_score += 4

#     authority_pressure = min(
#         25,
#         dominance + (5 if len(unique_domains) <= 8 else 0) + authority_pressure + link_score,
#     )

#     # 2. SERP FEATURE PRESSURE (0–10)
#     serp_features = serp.get("features", {})

#     feature_points = 0
#     feature_points += 3 if serp_features.get("people_also_ask") else 0
#     feature_points += 3 if serp_features.get("sitelinks") else 0
#     feature_points += min(2, len(serp.get("related_topics", [])))  
#     feature_points += min(2, len(serp.get("questions", [])))     

#     serp_feature_pressure = min(10, feature_points)

#     # 3. CONTENT DEPTH (0–15)
#     documents = scrape_context.get("documents", [])
#     avg_content = (
#         sum(d.get("content_length", 0) for d in documents) / len(documents)
#         if documents else 0
#     )

#     avg_headings = (
#         sum(len(d.get("headings", [])) for d in documents) / len(documents)
#         if documents else 0
#     )

#     content_depth = 0
#     if avg_content >= 2500:
#         content_depth += 5
#     elif avg_content >= 1200:
#         content_depth += 5

#     if avg_headings >= 15:
#         content_depth += 5
#     elif avg_headings >= 8:
#         content_depth += 3

#     in_headings = False

#     for d in documents:
#         # Check headings
#         for h in d.get("headings", []):
#             if keyword and keyword in h.lower():
#                 in_headings = True
#                 break

#     if in_headings:
#         content_depth += 5

#     content_depth = min(15, content_depth)
#     # 4. TITLE OPTIMIZATION BARRIER (0–15)
#     title_barrier = 0
#     # Count keyword in URL
#     kw_in_url = sum(1 for r in normalized_results if keyword and keyword in r.get("url", "").lower())
#     url_ratio = kw_in_url / max(1, len(normalized_results))

#     # Average title length
#     avg_title_length = (
#         sum(len(r.get("title", "")) for r in normalized_results)
#         / max(1, len(normalized_results))
#     )

#     # Count keyword in title
#     kw_in_title = sum(
#         1 for r in normalized_results
#         if keyword and keyword in r.get("title", "").lower()
#     )

#     intitle_ratio = kw_in_title / max(1, len(normalized_results))
    
#     if url_ratio >= 0.5:
#         title_barrier += 3
#     elif url_ratio >= 0.2:
#         title_barrier += 1

#     if 60 <= avg_title_length <= 75:
#         title_barrier += 6

#     if intitle_ratio >= 0.7:
#         title_barrier += 6


#     title_barrier = min(15, title_barrier)

#     # 5. INTENT LOCK (0–10)
#     intent_lock = 0

#     # Count how many competitors have the keyword intent as the top intent
#     intent_counts = {}
#     for c in competitors:
#         dist = c.get("intent_distribution", {})
#         for intent_name, value in dist.items():
#             if value > 0:
#                 intent_counts[intent_name] = intent_counts.get(intent_name, 0) + 1

#     # Find the most common intent among competitors
#     if intent_counts:
#         top_intent_count = max(intent_counts.values())
#         ratio = top_intent_count / max(1, len(competitors))
#         if ratio >= 0.7:
#             intent_lock = 10
#         elif ratio >= 0.5:
#             intent_lock = 5


#     # 6. FRESHNESS PRESSURE (0–10)
#     fresh_pages = sum(
#         1 for c in competitors
#         if c.get("freshness", {}).get("recent") == 1
#     )

#     freshness_pressure = 10 if fresh_pages >= 8 else 5 if fresh_pages >= 3 else 0

#     # 7. BRAND DOMINANCE (0–15)
#     brand_count = sum(1 for c in competitors if c.get("is_brand"))
#     brand_dominance = 15 if brand_count >= 6 else 7 if brand_count >= 3 else 0


#     # FINAL SCORE
#     score = min(
#         100,
#         authority_pressure
#         + serp_feature_pressure
#         + content_depth
#         + title_barrier
#         + intent_lock
#         + freshness_pressure
#         + brand_dominance
#     )

#     if score >= 75:
#         level = "very_hard"
#     elif score >= 55:
#         level = "hard"
#     elif score >= 35:
#         level = "medium"
#     else:
#         level = "easy"

#     return {
#         "seo_result": {
#             "keyword_difficulty": {
#                 "keyword": keyword,
#                 "difficulty_score": score,
#                 "difficulty_level": level,
#                 "difficulty_signals": {
#                     "authority_pressure": authority_pressure,
#                     "serp_feature_pressure": serp_feature_pressure,
#                     "content_depth": content_depth,
#                     "title_barrier": title_barrier,
#                     "intent_lock": intent_lock,
#                     "freshness_pressure": freshness_pressure,
#                     "brand_dominance": brand_dominance,
#                 },
#             }
#         }
#     }

from typing import Dict
from src.flow.states.wrext import WREXT
from src.flow.states.seo_state import SEORESULT


def keyword_difficulty_node(state: WREXT) -> Dict[str, SEORESULT]:
    serp = state.get("serp_normalized", {})
    competitors = state.get("competitors", [])
    documents = (state.get("scrape_context") or {}).get("documents", [])

    keyword = (state.get("serp_payload") or {}).get("query", "").lower()
    results = serp.get("normalize_results", [])[:10]

    # 1. LINK DIFFICULTY (PROXY) – 0–30
    link_score = 0

    # Domain repetition strength
    domain_freq = {}
    for r in results:
        d = r["domain"]
        domain_freq[d] = domain_freq.get(d, 0) + 1

    avg_repeat = sum(domain_freq.values()) / max(1, len(domain_freq))
    if avg_repeat >= 2.5:
        link_score += 12
    elif avg_repeat >= 1.8:
        link_score += 8
    elif avg_repeat >= 1.3:
        link_score += 4

    # Sitelinks = strong authority
    sitelink_ratio = sum(1 for c in competitors if c.get("has_sitelinks")) / max(1, len(competitors))
    if sitelink_ratio >= 0.6:
        link_score += 10
    elif sitelink_ratio >= 0.3:
        link_score += 5

    # Featured snippet ownership
    fs_ratio = sum(1 for c in competitors if c.get("featured_snippet")) / max(1, len(competitors))
    if fs_ratio >= 0.3:
        link_score += 8

    link_difficulty = min(30, link_score)

    # 2. DOMAIN MONOPOLY – 0–12
    unique_domains = len(set(r["domain"] for r in results))
    monopoly_ratio = unique_domains / max(1, len(results))

    if monopoly_ratio <= 0.5:
        domain_monopoly = 12
    elif monopoly_ratio <= 0.7:
        domain_monopoly = 7
    else:
        domain_monopoly = 2

    # 3. AUTHORITY PRESSURE – 0–12
    dominance = 0
    for c in competitors:
        for pos in c.get("top_positions", []):
            if pos <= 3:
                dominance += 3
            elif pos <= 6:
                dominance += 1

    authority_pressure = min(12, dominance)

    # 4. SERP FEATURE DENSITY – 0–14
    features = serp.get("features", {})
    feature_pressure = 0
    feature_pressure += 4 if features.get("people_also_ask") else 0
    feature_pressure += 4 if features.get("sitelinks") else 0
    feature_pressure += min(6, len(serp.get("questions", [])))

    serp_feature_pressure = min(14, feature_pressure)

    # 5. FRESHNESS PRESSURE – 0–10
    recent_ratio = sum(
        1 for c in competitors if c.get("freshness", {}).get("recent") == 1
    ) / max(1, len(competitors))

    if recent_ratio >= 0.6:
        freshness_pressure = 10
    elif recent_ratio >= 0.3:
        freshness_pressure = 5
    else:
        freshness_pressure = 0

    # 6. INTENT LOCK – 0–6
    intent_counts = {}
    for c in competitors:
        for i, v in c.get("intent_distribution", {}).items():
            if v > 0:
                intent_counts[i] = intent_counts.get(i, 0) + 1

    if intent_counts:
        top_ratio = max(intent_counts.values()) / max(1, len(competitors))
        intent_lock = 6 if top_ratio >= 0.7 else 3 if top_ratio >= 0.5 else 0
    else:
        intent_lock = 0

    # 7. ON-PAGE SATURATION – 0–6
    in_headings = False
    for d in documents:
        for h in d.get("headings", []):
            if keyword and keyword in h.lower():
                in_headings = True
                break

    onpage_pressure = 6 if in_headings else 2

    # 8. BRAND DOMINANCE – 0–10
    brand_ratio = sum(1 for c in competitors if c.get("is_brand")) / max(1, len(competitors))
    brand_dominance = 10 if brand_ratio >= 0.6 else 5 if brand_ratio >= 0.3 else 0

    # FINAL SCORE (Normalize to 100)
    raw_score = (
        link_difficulty
        + domain_monopoly
        + authority_pressure
        + serp_feature_pressure
        + freshness_pressure
        + intent_lock
        + onpage_pressure
        + brand_dominance
    )

    score = min(100, raw_score)

    if score >= 75:
        level = "very_hard"
    elif score >= 55:
        level = "hard"
    elif score >= 35:
        level = "medium"
    else:
        level = "easy"

    return {
        "seo_result": {
            "keyword_difficulty": {
                "keyword": keyword,
                "difficulty_score": score,
                "difficulty_level": level,
                "difficulty_signals": {
                    "link_difficulty": link_difficulty,
                    "domain_monopoly": domain_monopoly,
                    "authority_pressure": authority_pressure,
                    "serp_feature_pressure": serp_feature_pressure,
                    "freshness_pressure": freshness_pressure,
                    "intent_lock": intent_lock,
                    "onpage_pressure": onpage_pressure,
                    "brand_dominance": brand_dominance,
                },
            }
        }
    }
