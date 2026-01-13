from typing import Dict
from src.flow.states.wrext import WREXT
from src.flow.states.seo_state import SEORESULT


def keyword_difficulty_node(state: WREXT) -> Dict[str, SEORESULT]:
    serp = state.get("serp_normalized", {})
    competitors = state.get("competitors", [])
    documents = (state.get("scrape_context") or {}).get("documents", [])
    keyword = (state.get("serp_payload") or {}).get("query", "").lower()
    results = serp.get("normalize_results", [])[:10]
    normalized_results = serp.get("normalize_results", [])

    # 1. LINK DIFFICULTY (PROXY) – 0–20
    link_score = 0
    sitelink_ratio = sum(1 for c in competitors if c.get("has_sitelinks")) / max(1, len(competitors))
    if sitelink_ratio >= 0.3:
        link_score += 10
    elif sitelink_ratio >= 0.2:
        link_score += 5
    else:
        link_score += 0

    # Featured snippet ownership
    fs_ratio = sum(1 for c in competitors if c.get("featured_snippet")) / max(1, len(competitors))
    if fs_ratio >= 0.3:
        link_score += 10
    elif fs_ratio >= 0.1:
        link_score += 5
    else:
        link_score += 0

    link_difficulty = min(20, link_score)

    # 2. DOMAIN MONOPOLY – 0–10
    domain_monopoly = 0
    unique_domains = len(set(r["domain"] for r in results))
    monopoly_ratio = unique_domains / max(1, len(results))

    if monopoly_ratio <= 0.65:
        domain_monopoly = 10
    elif monopoly_ratio <= 0.85:
        domain_monopoly = 5
    else:
        domain_monopoly = 0

    # 3. AUTHORITY PRESSURE – 0–16
    authority_pressure = 0
    for c in competitors:
        for pos in c.get("top_positions", []):
            if pos <= 4:
                authority_pressure += 1

    avg_content = (
        sum(d.get("content_length", 0) for d in documents) / len(documents)
        if documents else 0
    )

    avg_content = avg_content / 10

    avg_headings = (
        sum(len(d.get("headings", [])) for d in documents) / len(documents)
        if documents else 0
    )
    if avg_content >= 3000:
        authority_pressure += 6
    elif avg_content >= 1800:
        authority_pressure += 3

    if avg_headings >= 35:
        authority_pressure += 6
    elif avg_headings >= 25:
        authority_pressure += 3

    authority_pressure = min(16, authority_pressure)

    # 4. SERP FEATURE DENSITY – 0–8
    features = serp.get("features", {})
    feature_pressure = 0
    feature_pressure += 4 if features.get("people_also_ask") else 0
    feature_pressure += min(4, len(serp.get("questions", [])))

    serp_feature_pressure = min(8, feature_pressure)

    # 5. FRESHNESS PRESSURE – 0–8
    recent_ratio = sum(
        1 for c in competitors if c.get("freshness", {}).get("recent") == 1
    ) / max(1, len(competitors))

    if recent_ratio >= 0.8:
        freshness_pressure = 8
    elif recent_ratio >= 0.4:
        freshness_pressure = 4
    else:
        freshness_pressure = 0

    # 6. INTENT LOCK – 0–14
    intent_counts = {}
    for c in competitors:
        for i, v in c.get("intent_distribution", {}).items():
            if v > 0:
                intent_counts[i] = intent_counts.get(i, 0) + 1

    if intent_counts:
        top_ratio = max(intent_counts.values()) / max(1, len(competitors))
        intent_lock = 14 if top_ratio >= 0.8 else 7 if top_ratio >= 0.5 else 0

    # 7. ON-PAGE SATURATION – 0–9
    onpage_pressure = 0
    # Count keyword in URL
    kw_in_url = sum(1 for r in normalized_results if keyword and keyword in r.get("url", "").lower())
    url_ratio = kw_in_url / max(1, len(normalized_results))

    # Average title length
    avg_title_length = (
        sum(len(r.get("title", "")) for r in normalized_results)
        / max(1, len(normalized_results))
    )
    # Count keyword in title
    kw_in_title = sum(
        1 for r in normalized_results
        if keyword and keyword in r.get("title", "").lower()
    )
    intitle_ratio = kw_in_title / max(1, len(normalized_results))
    
    if url_ratio >= 0.2:
        onpage_pressure += 3

    if 65 <= avg_title_length <= 75:
        onpage_pressure += 3
    elif 50 <= avg_title_length <= 80:
        onpage_pressure += 2

    if intitle_ratio >= 0.2:
        onpage_pressure += 3


    onpage_pressure = min(9, onpage_pressure)

    # 8. BRAND DOMINANCE – 0–15
    brand_ratio = sum(1 for c in competitors if c.get("is_brand")) / max(1, len(competitors))
    brand_dominance = 15 if brand_ratio >= 0.8 else 8 if brand_ratio >= 0.4 else 0

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
                    # "monopoly_ratio": monopoly_ratio,
                    # "fs_ratio": fs_ratio,
                    # "sitelink_ratio": sitelink_ratio,
                    # "avg_content": avg_content,
                    # "avg_headings": avg_headings,
                    # "recent_ratio": recent_ratio,
                    # "url_ratio": url_ratio,
                    # "intitle_ratio": intitle_ratio,
                    # "brand_ratio": brand_ratio,
                    # "top_ratio": top_ratio,
                    # "avg_title_length": avg_title_length,
                },
            }
        }
    }
