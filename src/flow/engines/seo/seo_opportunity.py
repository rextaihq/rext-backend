from src.flow.utils.intent_utils import get_consensus_intent

def seo_opportunity_node(state: REXT) -> Dict[str, SEORESULT]:
    seo = state.get("seo_result", {})

    kd = seo.get("keyword_difficulty", {})
    gaps = seo.get("content_gaps", {})
    serp = state.get("serp_normalized", {})
    competitors = state.get("competitors", [])

    # Unified KD State usage
    difficulty_score = kd.get("difficulty_score", 100)
    difficulty_level = kd.get("difficulty_level", "very_hard")
    breakdown = kd.get("breakdown", {})

    missing_topics = gaps.get("missing_topics", [])
    missing_questions = gaps.get("missing_questions", [])
    weak_areas = gaps.get("weak_coverage_areas", [])

    # 1. OPPORTUNITY SCORE (0–100)
    score = 0

    # Difficulty inverse (easy = more opportunity)
    if difficulty_level == "easy":
        score += 40
    elif difficulty_level == "medium":
        score += 25
    elif difficulty_level == "hard":
        score += 10
    else:
        score += 0

    # Content gaps
    score += min(20, len(missing_topics) * 4)
    score += min(15, len(missing_questions) * 3)
    score += min(15, len(weak_areas) * 3)

    # Brand dominance penalty
    brand_penalty = breakdown.get("brand_dominance", 0)
    score -= brand_penalty * 0.5

    # Freshness penalty
    score -= breakdown.get("freshness_pressure", 0) * 0.3

    # SERP feature opportunity
    features = serp.get("features", {})
    if features.get("people_also_ask"):
        score += 5
    if features.get("featured_snippet"):
        score += 5

    score = max(0, min(100, int(score)))

    # 2. OPPORTUNITY LEVEL
    if score >= 65:
        opportunity_level = "high"
    elif score >= 30:
        opportunity_level = "medium"
    else:
        opportunity_level = "low"

    # 3. STRATEGY DERIVATION
    # 🔍 REINFORCEMENT: Use both API intent and Competitor consensus
    serp_backlinks = seo.get("serp_backlinks", {})
    api_intent = serp_backlinks.get("main_intent", "informational")
    intent = get_consensus_intent(api_intent, competitors)

    recommended_content_type = (
        "comparison" if intent == "commercial"
        else "landing_page" if intent == "transactional"
        else "blog"
    )

    avg_competitor_length = 0
    docs = (state.get("scrape_context") or {}).get("documents", [])
    if docs:
        avg_competitor_length = int(
            sum(d.get("content_length", 0) for d in docs) / len(docs)
        )

    ideal_word_count = max(1200, avg_competitor_length + 300)

    ranking_time = (
        "1–2 months" if difficulty_level == "easy"
        else "3–4 months" if difficulty_level == "medium"
        else "6+ months"
    )

    content_angle = (
        "Gap-focused guide answering missed questions"
        if missing_questions
        else "More comprehensive & structured content"
    )

    # 4. OUTPUT
    return {
        "seo_result": {
            **seo,
            "seo_strategy": {
                "target_intent": intent,
                "recommended_content_type": recommended_content_type,
                "ideal_word_count": ideal_word_count,
                "priority_topics": missing_topics[:5],
                "questions_to_answer": missing_questions[:5],
                "difficulty": difficulty_level,
                "ranking_time_estimate": ranking_time,
                "content_angle": content_angle,
            },
            "seo_opportunity": {
                "opportunity_score": score,
                "opportunity_level": opportunity_level,
                "key_drivers": {
                    "missing_topics": (missing_topics),
                    "missing_questions": (missing_questions),
                    "brand_pressure": breakdown.get("brand_dominance", 0),
                    "freshness_pressure": breakdown.get("freshness_pressure", 0),
                },
            },
        }
    }
