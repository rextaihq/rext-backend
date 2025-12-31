# # src/flow/engines/seo/seo_opportunity.py

# from typing import Dict, Any
# from src.flow.states.wrext import WREXT

# def seo_opportunity_node(state: WREXT) -> Dict[str, Any]:
#     seo = state.get("seo_result", {})
#     serp = state.get("serp_normalized", {})

#     # Pull values with safe defaults
#     keyword_score = seo.get("keyword_score", {}).get("score", 0)
#     difficulty = seo.get("keyword_difficulty", {}).get("difficulty_score", 50)  # neutral default
#     gap_score = seo.get("competitor_gap", {}).get("gap_score", 0)

#     # Base opportunity (weighted)
#     base_value = (keyword_score * 0.5) + (gap_score * 0.5)
    
#     # Difficulty dampening
#     difficulty_penalty = difficulty * 0.7
#     opportunity = base_value - difficulty_penalty

#     # SERP feature adjustments
#     features = serp.get("features", {})
#     feature_count = sum(1 for v in features.values() if v)

#     if feature_count >= 4:
#         opportunity -= 10  # CTR loss due to SERP features
#     elif feature_count >= 2:
#         opportunity -= 5

#     # Intent diversity penalty
#     intent = serp.get("intent", {})
#     intent_types = len(intent.keys()) if isinstance(intent, dict) else 0
#     if intent_types > 2:
#         opportunity -= 10  # Mixed intent penalty

#     # Freshness penalty
#     freshness = serp.get("freshness", {})
#     recent = freshness.get("recent", 0)
#     older = freshness.get("older", 0)
#     total = recent + older
#     is_fresh = total > 0 and (recent / total) > 0.3

#     if is_fresh:
#         opportunity -= 5  # News-driven SERP

#     # Clamp & normalize
#     opportunity = int(max(0, min(100, opportunity)))

#     # Opportunity level
#     if opportunity >= 65:
#         level = "high"
#     elif opportunity >= 35:
#         level = "medium"
#     else:
#         level = "low"

#     # Return structured result
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
#                     "intent_types_detected": intent_types,
#                     "freshness_ratio": recent / max(1, total),
#                     "is_fresh": is_fresh,
#                 },
#                 "explanation": [
#                     f"Keyword value score: {keyword_score}",
#                     f"Competitor gap score: {gap_score}",
#                     f"Difficulty penalty applied: {difficulty_penalty}",
#                     f"Active SERP features: {feature_count}",
#                     f"Intent types detected: {intent_types}",
#                     f"Freshness ratio: {recent}/{total} ({is_fresh})"
#                 ],
#             }
#         }
#     }
