# # src/flow/engines/seo/seo_opportunity.py

# from typing import Dict, Any
# from src.flow.states.wrext import WREXT

# def seo_opportunity_node(state: WREXT) -> Dict[str, Any]:
#     seo = state.get("seo_result", {})
#     serp = state.get("serp_normalized", {})

#     keyword_score = seo.get("keyword_score", {}).get("score", 0)
#     difficulty = seo.get("keyword_difficulty", {}).get("difficulty_score", 100)
#     gap_score = seo.get("competitor_gap", {}).get("gap_score", 0)

#     # -------------------------------------------------
#     # 1. Base Opportunity (Weighted)
#     # -------------------------------------------------
#     base_value = (
#         (keyword_score * 0.5) +
#         (gap_score * 0.5)
#     )

#     # -------------------------------------------------
#     # 2. Difficulty Dampening (Non-linear)
#     # -------------------------------------------------
#     difficulty_penalty = difficulty * 0.7
#     opportunity = base_value - difficulty_penalty

#     # -------------------------------------------------
#     # 3. SERP Risk Adjustments
#     # -------------------------------------------------
#     features = serp.get("features", {})
#     feature_count = sum(1 for v in features.values() if v)

#     if feature_count >= 4:
#         opportunity -= 10  # CTR loss
#     elif feature_count >= 2:
#         opportunity -= 5

#     intent = serp.get("intent", {})
#     if isinstance(intent, dict) and len(intent) > 2:
#         opportunity -= 10  # Mixed intent penalty

#     freshness = serp.get("freshness", {})
#     if freshness.get("is_fresh", False):
#         opportunity -= 5  # News-driven SERP

#     # -------------------------------------------------
#     # 4. Clamp & Normalize
#     # -------------------------------------------------
#     opportunity = int(max(0, min(100, opportunity)))

#     # -------------------------------------------------
#     # 5. Opportunity Level
#     # -------------------------------------------------
#     if opportunity >= 65:
#         level = "high"
#     elif opportunity >= 35:
#         level = "medium"
#     else:
#         level = "low"

#     return {
#         "seo_result": {
#             "seo_opportunity": {
#                 "opportunity_score": opportunity,
#                 "level": level,
#                 "signals": {
#                     "keyword_score": keyword_score,
#                     "gap_score": gap_score,
#                     "difficulty_score": difficulty,
#                     "serp_features": feature_count,
#                     "freshness": freshness.get("is_fresh", False),
#                 },
#                 "explanation": [
#                     f"Keyword value score: {keyword_score}",
#                     f"Competitor gap score: {gap_score}",
#                     f"Difficulty dampening: {difficulty}",
#                     f"Active SERP features: {feature_count}",
#                 ],
#             }
#         }
#     }
