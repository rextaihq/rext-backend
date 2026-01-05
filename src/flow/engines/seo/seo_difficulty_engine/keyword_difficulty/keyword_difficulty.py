from src.flow.states.wrext import WREXT

from src.flow.engines.seo.seo_difficulty_engine.keyword_difficulty.link_difficulty import link_difficulty_score
from src.flow.engines.seo.seo_difficulty_engine.keyword_difficulty.serp_score import serp_saturation_score

from src.flow.engines.seo.seo_difficulty_engine.keyword_difficulty.content_difficulty import content_difficulty_score
from src.flow.engines.seo.seo_difficulty_engine.keyword_difficulty.context_modifier import context_modifier
from src.flow.states.seo_state import KeywordDifficultyState

def calculate_final_kd(
    keyword: str,
    keyword_intent: str,
    wrext_data: WREXT
) -> dict:
    """
    Calculate full Keyword Difficulty (KD) using:
    - Part1: Link Difficulty Score
    - Part2: SERP Saturation Score
    - Part3: Content Difficulty Score
    - Part4: Context Modifier
    Returns structured breakdown.
    """

    # --------------------------
    # 1️⃣ Part-1: Link Difficulty Score
    # --------------------------
    serp_normalized = wrext_data.get("serp_normalized", {}).get("normalize_results", [])
    competitors = wrext_data.get("competitors", [])

    link_score_result = link_difficulty_score(
        keyword=keyword,
        competitors=competitors,
        serp_normalized=serp_normalized
    )
    link_score = link_score_result["link_difficulty"]  # 0–100

    # --------------------------
    # 2️⃣ Part-2: SERP Saturation Score
    # --------------------------
    serp_score_result = serp_saturation_score(
        serp_normalized=wrext_data["serp_normalized"],
        competitors=competitors
    )
    serp_score = serp_score_result["serp_saturation_score"]  # 0–100

    # --------------------------
    # 3️⃣ Part-3: Content Difficulty Score
    # --------------------------
    content_score_result = content_difficulty_score(
        keyword_intent=keyword_intent,
        normalized_results=serp_normalized,
        competitors=competitors,
        scrape_context = wrext_data.get("scrape_context", {})
    )
    content_score = content_score_result["content_difficulty_score"]  # 0–100

    # --------------------------
    # 4️⃣ Part-4: Context Modifier (±5)
    # --------------------------
    context_modifier_value = context_modifier(
        competitors=competitors,
        serp_normalized=wrext_data["serp_normalized"],
        keyword_intent=keyword_intent
    )

    # --------------------------
    # 5️⃣ Final KD Calculation
    # --------------------------
    kd = 0.50 * link_score + 0.25 * serp_score + 0.20 * content_score + context_modifier_value
    kd = max(0, min(kd, 100))  # clamp between 0–100

    # --------------------------
    # 6️⃣ Notes / Explanation
    # --------------------------
    # Brand dominance
    brands = {"brand", "publisher", "gov", "edu"}
    domain_stats = wrext_data.get("serp_normalized", {}).get("domain_stats", {})
    brand_count = sum(1 for c in competitors
                      if domain_stats.get(c["domain"], {}).get("type") in brands)
    
    # Map brand count to 0-15 scale (approx matching Approach 1 logic)
    brand_dominance = 15 if brand_count >= 6 else 7 if brand_count >= 3 else 0

    # Freshness pressure
    fresh_pages = sum(
        1 for c in competitors
        if c.get("freshness", {}).get("recent") == 1
    )
    freshness_pressure = 10 if fresh_pages >= 8 else 5 if fresh_pages >= 3 else 0

    # --------------------------
    # 7️⃣ Notes / Explanation
    # --------------------------
    notes = []

    if brand_count >= len(competitors) * 0.5:
        notes.append("High brand dominance")

    # SERP features
    if wrext_data["serp_normalized"].get("features", {}).get("top_stories", False):
        notes.append("Top Stories present")
    if any(c.get("featured_snippet", False) for c in competitors):
        notes.append("Featured snippet present")

    # Backlinks
    if link_score > 70:
        notes.append("Strong backlink profiles in top URLs")

    # --------------------------
    # 8️⃣ Return structured output
    # --------------------------
    return {
        "keyword": keyword,
        "kd": round(kd, 2),
        "breakdown": {
            "link_score": round(link_score, 2),
            "serp_score": round(serp_score, 2),
            "content_score": round(content_score, 2),
            "context_modifier": round(context_modifier_value, 2),
            "brand_dominance": brand_dominance,
            "freshness_pressure": freshness_pressure
        },
        "notes": notes
    }


def compute_keyword_difficulty(wrext_data: WREXT) -> WREXT:
    """
    Node function to calculate final Keyword Difficulty (KD)
    Stores results in wrext_data['seo_result']['keyword_difficulty']
    """
    # wrext_data.setdefault("seo_result", {})

    keyword = wrext_data["serp_normalized"]["query"]
    # Default intent to informational if not found
    keyword_intent = (wrext_data.get("seo_result") or {}).get("intent", {}).get("primary_intent", "informational")

    # Calculate KD
    kd_result = calculate_final_kd(
        keyword=keyword,
        keyword_intent=keyword_intent,
        wrext_data=wrext_data
    )
    
    score = kd_result["kd"]
    if score >= 75:
        level = "very_hard"
    elif score >= 55:
        level = "hard"
    elif score >= 35:
        level = "medium"
    else:
        level = "easy"

    prev_seo = wrext_data.get("seo_result", {})

    return {
        "seo_result": {
            **prev_seo,
            "keyword_difficulty": {
                "keyword": kd_result["keyword"],
                "difficulty_score": score,
                "difficulty_level": level,
                "breakdown": kd_result["breakdown"],
                "notes": kd_result["notes"],
            }
        }
    }
