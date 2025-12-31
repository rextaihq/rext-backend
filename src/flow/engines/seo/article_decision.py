# # src/flow/engines/seo/article_decision.py

# from typing import Dict, Any
# from src.flow.states.wrext import WREXT

# def article_decision_node(state: WREXT) -> Dict[str, Any]:
#     seo = state.get("seo_result", {})
#     opportunity = seo.get("seo_opportunity", {"opportunity_score":0, "recommendation":"skip"})
#     score = opportunity.get("opportunity_score", 0)
#     recommendation = opportunity.get("recommendation", "skip")

#     # Decision rules
#     should_generate = recommendation == "go"
#     confidence = "high" if score >= 70 else "medium" if score >= 50 else "low"
#     reason = f"Opportunity score: {score}, Recommendation: {recommendation}"

#     seo_result = seo
#     seo_result["article_decision"] = {
#         "should_generate": should_generate,
#         "confidence": confidence,
#         "reason": reason
#     }

#     return {"seo_result": seo_result}
