from typing import Dict, Any
from src.flow.states.wrext import WREXT


def keyword_difficulty_node(state: WREXT) -> Dict[str, Any]:
    competitors = state.get("competitors", [])
    serp = state.get("serp_normalized", {})
    features = serp.get("features", {})
    serp_intent = serp.get("intent", {}).get("primary")

    # --------------------------------------------------
    # 1️⃣ SERP DOMINANCE & DOMAIN CONCENTRATION (30)
    # --------------------------------------------------
    unique_domains = set()
    dominance_points = 0
    sitelink_domains = set()
    featured_snippet_domains = set()

    for comp in competitors:
        domain = comp.get("domain")
        if domain:
            unique_domains.add(domain)

        for pos in comp.get("top_positions", []):
            if pos <= 3:
                dominance_points += 3
            elif pos <= 5:
                dominance_points += 2
            elif pos <= 10:
                dominance_points += 1

        if comp.get("has_sitelinks"):
            sitelink_domains.add(domain)

        if comp.get("featured_snippet"):
            featured_snippet_domains.add(domain)

    domain_concentration_score = 0
    if len(unique_domains) <= 4:
        domain_concentration_score = 10
    elif len(unique_domains) <= 7:
        domain_concentration_score = 5

    authority_score = min(
        30,
        dominance_points +
        domain_concentration_score +
        (5 if len(sitelink_domains) >= 2 else 0) +
        (5 if featured_snippet_domains else 0)
    )

    # --------------------------------------------------
    # 2️⃣ SERP CROWDING / FEATURE PRESSURE (20)
    # --------------------------------------------------
    crowding_features = [
        "featured_snippet",
        "people_also_ask",
        "knowledge_graph",
        "local_pack",
        "video_carousel",
        "shopping_results"
    ]

    active_features = sum(1 for f in crowding_features if features.get(f))
    crowding_score = min(20, active_features * 4)

    # --------------------------------------------------
    # 3️⃣ CONTENT DEPTH BARRIER (15)
    # --------------------------------------------------
    avg_snippet_length = (
        sum(c.get("avg_snippet_length", 0) for c in competitors) / len(competitors)
        if competitors else 0
    )

    content_score = 0
    if avg_snippet_length >= 250:
        content_score = 15
    elif avg_snippet_length >= 150:
        content_score = 8

    # --------------------------------------------------
    # 4️⃣ TITLE OPTIMIZATION BARRIER (10)
    # --------------------------------------------------
    normalized_results = serp.get("normalize_results", [])
    avg_title_length = (
        sum(len(r.get("title", "")) for r in normalized_results) /
        max(1, len(normalized_results))
    )

    title_score = 0
    if 65 <= avg_title_length <= 75:
        title_score = 10
    elif 60 <= avg_title_length <= 80:
        title_score = 5
    else:
        title_score = 0

    # --------------------------------------------------
    # 5️⃣ INTENT LOCK (10) — WREXT SAFE
    # --------------------------------------------------
    intent_score = 0

    if serp_intent:
        matching_intent_competitors = sum(
            1 for c in competitors
            if c.get("intent_distribution", {}).get(serp_intent, 0) > 0
        )

        intent_ratio = matching_intent_competitors / max(1, len(competitors))

        if intent_ratio >= 0.7:
            intent_score = 10
        elif intent_ratio >= 0.5:
            intent_score = 5

    # --------------------------------------------------
    # 6️⃣ FRESHNESS PRESSURE (10)
    # --------------------------------------------------
    fresh_pages = sum(
        1 for c in competitors
        if c.get("freshness", {}).get("last_6_months", 0) > 0
    )

    freshness_score = 0
    if fresh_pages >= 5:
        freshness_score = 10
    elif fresh_pages >= 3:
        freshness_score = 5

    # --------------------------------------------------
    # 7️⃣ SERP STABILITY / VOLATILITY (5)
    # --------------------------------------------------
    stable_competitors = sum(
        1 for c in competitors
        if c.get("total_occurrences", 0) >= 3
    )

    stability_score = 0
    if stable_competitors >= 6:
        stability_score = 5
    elif stable_competitors >= 4:
        stability_score = 3

    # --------------------------------------------------
    # FINAL DIFFICULTY SCORE
    # --------------------------------------------------
    final_score = min(
        100,
        authority_score +
        crowding_score +
        content_score +
        title_score +
        intent_score +
        freshness_score +
        stability_score
    )

    if final_score >= 75:
        level = "very_hard"
    elif final_score >= 55:
        level = "hard"
    elif final_score >= 35:
        level = "medium"
    else:
        level = "easy"

    return {
        "seo_result": {
            "keyword_difficulty": {
                "difficulty_score": final_score,
                "difficulty_level": level,
                "signals": {
                    "serp_dominance": authority_score,
                    "feature_pressure": crowding_score,
                    "content_depth": content_score,
                    "title_barrier": title_score,
                    "intent_lock": intent_score,
                    "freshness_pressure": freshness_score,
                    "serp_stability": stability_score
                }
            }
        }
    }