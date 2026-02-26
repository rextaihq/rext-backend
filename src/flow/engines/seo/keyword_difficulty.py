from typing import Dict
from src.flow.states.rext import REXT
from src.flow.states.seo_state import SEORESULT
# from src.flow.engines.seo.dataforseo_response import get_dataforseo_data


def keyword_difficulty_node(state: REXT) -> Dict[str, SEORESULT]:
    serp = state.get("serp_normalized", {})
    competitors = state.get("competitors", [])
    keyword = (state.get("serp_payload") or {}).get("query", "").lower()
    results = serp.get("normalize_results", [])[:10]
    normalized_results = serp.get("normalize_results", [])
    
    # Access serp_backlinks from seo_result
    seo_result = state.get("seo_result", {})
    dataforseo_data = seo_result.get("serp_backlinks", {})

    # 1. LINK DIFFICULTY (PROXY) – 0–20
    
    backlinks = dataforseo_data.get("backlinks", 0)
    referring_domains = dataforseo_data.get("referring_domains", 0)
    dofollow_links = dataforseo_data.get("dofollow_links", 0)
    images = dataforseo_data.get("images", False)
    videos = dataforseo_data.get("videos", False)
    monthly_search_volume = dataforseo_data.get("search_volume", 0)
    main_intent = dataforseo_data.get("main_intent", "")
    link_score = 0

    if backlinks >= 5000:
        link_score += 20
    elif backlinks >= 3500:
        link_score += 10
    elif backlinks >= 2000:
        link_score += 5
    else:
        link_score += 0

    if referring_domains >= 1000:
        link_score += 15
    elif referring_domains >= 600:
        link_score += 10
    elif referring_domains >=300:
        link_score += 5
    else:
        link_score += 0

    if dofollow_links >= 5000:
        link_score += 15
    elif dofollow_links >= 3500:
        link_score += 10
    elif dofollow_links >=2000:
        link_score += 5
    else:
        link_score += 0

    unique_domains = len(set(r["domain"] for r in results))
    monopoly_ratio = unique_domains / max(1, len(results))

    if monopoly_ratio <= 0.7:
        link_score += 15
    elif monopoly_ratio <= 0.8:
        link_score += 10
    elif monopoly_ratio <= 0.9:
        link_score += 5

    link_difficulty = min(65, link_score)

    # 2. SERP FEATURE DENSITY – 0–6
    features = serp.get("features", {})
    feature_pressure = 0
    feature_pressure += 3 if features.get("people_also_ask") else 0
    feature_pressure += min(3, len(serp.get("questions", [])))

    serp_feature_pressure = min(6, feature_pressure)

    # 3. FRESHNESS PRESSURE – 0–5
    recent_ratio = sum(
        1 for c in competitors if c.get("freshness", {}).get("recent") == 1
    ) / max(1, len(competitors))

    if recent_ratio >= 0.8:
        freshness_pressure = 5
    elif recent_ratio >= 0.5:
        freshness_pressure = 2
    else:
        freshness_pressure = 0

    # 4. ON-PAGE SATURATION – 0–9
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

    if 50 <= avg_title_length <= 80:
        onpage_pressure += 3

    if intitle_ratio >= 0.2:
        onpage_pressure += 3


    onpage_pressure = min(9, onpage_pressure)

    # 5. BRAND DOMINANCE – 0–15
    brand_ratio = sum(1 for c in competitors if c.get("is_brand")) / max(1, len(competitors))
    brand_dominance = 15 if brand_ratio >= 0.8 else 7 if brand_ratio >= 0.4 else 0

    # FINAL SCORE (Normalize to 100)
    raw_score = (
        link_difficulty
        + serp_feature_pressure
        + freshness_pressure
        + onpage_pressure
        + brand_dominance
    )

    if images:
        raw_score -= 5
    if videos:
        raw_score -= 5

    score = min(100, raw_score)

    if score >= 70:
        level = "very_hard"
    elif score >= 50:
        level = "hard"
    elif score >= 30:
        level = "medium"
    else:
        level = "easy"

    return {
        "seo_result": {
            "keyword_difficulty": {
                "keyword": keyword,
                "difficulty_score": score,
                "difficulty_level": level,
                "breakdown": {
                    "link_score": link_difficulty,
                    "serp_score": serp_feature_pressure,
                    "freshness_pressure": freshness_pressure,
                    "onpage_pressure": onpage_pressure,
                    "brand_dominance": brand_dominance,
                },
                "notes": [
                    f"Main intent: {main_intent}",
                    f"Monthly search volume: {monthly_search_volume}"
                ]
            }
        }
    }