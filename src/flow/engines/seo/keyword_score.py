# from typing import Dict, Any
# from src.flow.states.wrext import WREXT

# def keyword_score_node(state: WREXT) -> Dict[str, Any]:
#     serp = state.get("serp_normalized", {})
#     competitors = state.get("competitors", [])
#     seo = state.get("seo_result", {})
#     keywords = seo.get("extracted_keywords", {}).get("all", [])

#     if not keywords:
#         return {}

#     organic_results = serp.get("normalize_results", [])
#     related_topics = len(serp.get("related_topics", []))
#     questions = len(serp.get("questions", []))
#     unique_domains = set(r.get("domain") for r in organic_results if r.get("domain"))

#     # 1. Semantic Score (Related Topics & Questions)
#     semantic_score = min(30, (related_topics * 3) + (questions * 3))

#     # 2. SERP Structure (Depth & Domain Diversity)
#     serp_depth_score = min(15, len(organic_results))
#     domain_diversity_score = min(10, len(unique_domains))
#     serp_structure_score = serp_depth_score + domain_diversity_score

#     # 3. Intent Diversity (from competitors if available)
#     serp_intent_types = len(serp.get("intent", {})) if serp.get("intent") else 1
#     competitor_intents = set()
#     for c in competitors:
#         competitor_intents.update(c.get("intent_distribution", {}).keys())
#     intent_diversity_score = min(15, serp_intent_types + len(competitor_intents))

#     # 4. Freshness (SERP + Competitors)
#     freshness_signal = serp.get("freshness", {})
#     freshness_score = 0
#     if freshness_signal.get("recent", 0) / max(1, freshness_signal.get("recent", 0) + freshness_signal.get("older", 0)) > 0.3:
#         freshness_score += 7
#     avg_comp_freshness = sum(sum(c.get("freshness", {}).values()) for c in competitors) / max(1, len(competitors))
#     if avg_comp_freshness > 1:
#         freshness_score += 8
#     freshness_score = min(15, freshness_score)

#     # 5. Optimization Opportunity (Titles & Snippets)
#     titles = [r.get("title", "") for r in organic_results]
#     avg_title_len = sum(len(t) for t in titles) / len(titles) if titles else 0
#     snippets = [c.get("avg_snippet_length", 0) for c in competitors]
#     avg_snippet_len = sum(snippets) / len(snippets) if snippets else 0

#     optimization_score = 0
#     if 65 < avg_title_len < 75:
#         optimization_score += 7
#     if 150 < avg_snippet_len < 170:
#         optimization_score += 8

#     # 6. SERP Features Penalty
#     features = serp.get("features", {})
#     active_features = sum(1 for v in features.values() if v)
#     serp_feature_penalty = min(15, active_features * 3)

#     # Final Score
#     raw_score = (
#         semantic_score +
#         serp_structure_score +
#         intent_diversity_score +
#         freshness_score +
#         optimization_score
#         - serp_feature_penalty
#     )
#     score = max(0, min(100, raw_score))

#     strength = "low"
#     if score >= 70:
#         strength = "high"
#     elif score >= 40:
#         strength = "medium"

#     return {
#         "seo_result": {
#             "keyword_score": {
#                 "score": score,
#                 "strength": strength,
#                 "signals": {
#                     "related_topics": related_topics,
#                     "questions": questions,
#                     "serp_results": len(organic_results),
#                     "unique_domains": len(unique_domains),
#                     "intent_types": serp_intent_types,
#                     "competitor_intents": len(competitor_intents),
#                     "avg_title_length": round(avg_title_len, 1),
#                     "avg_snippet_length": round(avg_snippet_len, 1),
#                     "freshness_score": freshness_score,
#                     "serp_features_penalty": serp_feature_penalty,
#                 }
#             }
#         }
#     }
