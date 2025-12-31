# from typing import Dict, Any
# from src.flow.states.wrext import WREXT


# def competitor_gap_node(state: WREXT) -> Dict[str, Any]:
#     serp = state.get("serp_normalized", {})
#     competitors = state.get("competitors", [])
#     organic_results = serp.get("normalize_results", [])

#     related_topics = set(serp.get("related_topics", []))
#     questions = set(serp.get("questions", []))
#     features = serp.get("features", {})

#     gap_score = 0
#     reasons = []

#     # -------------------------------------------------
#     # 1. Semantic Depth Gap (Max 25)
#     # -------------------------------------------------
#     if len(related_topics) >= 5:
#         gap_score += 25
#         reasons.append("Competitors lack semantic topic coverage")

#     # -------------------------------------------------
#     # 2. Question Coverage Gap (Max 20)
#     # -------------------------------------------------
#     if len(questions) >= 4:
#         gap_score += 20
#         reasons.append("People Also Ask questions not fully addressed")

#     # -------------------------------------------------
#     # 3. Content Thinness Gap (Max 15)
#     # -------------------------------------------------
#     avg_snippet_len = sum(
#         c.get("avg_snippet_length", 0) for c in competitors
#     ) / max(1, len(competitors))

#     if avg_snippet_len < 150:
#         gap_score += 15
#         reasons.append("Competitor content appears thin or shallow")

#     # -------------------------------------------------
#     # 4. Intent Misalignment Gap (Max 15)
#     # -------------------------------------------------
#     intent_types = set()
#     for c in competitors:
#         intent_types.update(c.get("intent_distribution", {}).keys())

#     if len(intent_types) <= 1:
#         gap_score += 15
#         reasons.append("Competitors focus on a single search intent")

#     # -------------------------------------------------
#     # 5. Freshness Gap (Max 10)
#     # -------------------------------------------------
#     stale_competitors = sum(
#         1 for c in competitors if sum(c.get("freshness", {}).values()) == 0
#     )

#     if stale_competitors >= len(competitors) * 0.5:
#         gap_score += 10
#         reasons.append("Many competitors have outdated content")

#     # -------------------------------------------------
#     # 6. SERP Feature Gap (Max 10)
#     # -------------------------------------------------
#     if features.get("featured_snippet") and not any(
#         c.get("featured_snippet") for c in competitors
#     ):
#         gap_score += 10
#         reasons.append("Featured snippet is available but not strongly owned")

#     # -------------------------------------------------
#     # 7. Internal Linking / SERP Dominance Gap (Max 5)
#     # -------------------------------------------------
#     if not any(c.get("has_sitelinks") for c in competitors):
#         gap_score += 5
#         reasons.append("Competitors show weak internal linking")

#     gap_score = min(100, gap_score)

#     return {
#         "seo_result": {
#             "competitor_gap": {
#                 "gap_score": gap_score,
#                 "missing_topics": list(related_topics),
#                 "missing_questions": list(questions),
#                 "weak_areas": reasons,
#                 "signals": {
#                     "avg_snippet_length": round(avg_snippet_len, 1),
#                     "intent_types_detected": list(intent_types),
#                     "stale_competitors": stale_competitors,
#                     "serp_features": [k for k, v in features.items() if v],
#                     "organic_results": len(organic_results),
#                 }
#             }
#         }
#     }
