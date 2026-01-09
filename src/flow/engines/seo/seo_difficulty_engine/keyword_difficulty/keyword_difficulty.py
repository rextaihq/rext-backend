from src.flow.states.wrext import WREXT, Competitor, NormalizedOrganicResult, SERPNORMALIZED
from typing import List, Dict, Any
from src.flow.engines.seo.seo_difficulty_engine.keyword_difficulty.link_difficulty import competitor_link_kd
from src.flow.engines.seo.seo_difficulty_engine.keyword_difficulty.serp_score import competitor_serp_kd
from src.flow.engines.seo.seo_difficulty_engine.keyword_difficulty.content_difficulty import content_strength
from src.flow.engines.seo.seo_difficulty_engine.keyword_difficulty.context_modifier import context_modifier
import statistics
from src.flow.engines.seo.seo_difficulty_engine.utils.utils import INTENT_WEIGHTS
def calculate_final_kd(keyword: str, keyword_intent: str, wrext_data: WREXT) -> dict:
    """
    NEW APPROACH:
    For each competitor:
        total_kd = link_kd + serp_kd + content_kd
    Final KD = median(all total_kd values)
    Context modifier ignored for now.
    """
    weights = INTENT_WEIGHTS.get(keyword_intent, INTENT_WEIGHTS["informational"])

    serp_normalized = wrext_data.get("serp_normalized", {}).get("normalize_results", [])
    competitors = wrext_data.get("competitors", [])
    scrape_context = wrext_data.get("scrape_context", {})

    competitor_total_kds = []

    breakdown_details = []

    for comp in competitors:
        # Find corresponding normalized result for this competitor
        nr = next(
        (
            res
            for res in serp_normalized
            if res["domain"] == comp["domain"]
            and res["position"] in comp["top_positions"]
        ),
        None
        )


        # 1️⃣ Link KD per competitor
        link_kd = competitor_link_kd(keyword=keyword, comp=comp, serp_entry=nr or {}, normalized_results=serp_normalized, competitors=competitors)

        # 2️⃣ SERP KD per competitor
        serp_kd = competitor_serp_kd(comp=comp, serp_normalized=wrext_data.get("serp_normalized", {}), competitors=competitors)

        # 3️⃣ Content KD per competitor
        content_kd = content_strength(keyword_intent=keyword_intent, competitor=comp, normalized_result=nr, scrape_data=scrape_context) if nr else 0



        # weights = INTENT_WEIGHTS.get(keyword_intent, INTENT_WEIGHTS["informational"])

        total_kd = (
            link_kd * weights["link"] +
            serp_kd * weights["serp"] +
            content_kd * weights["content"]
        )


        # total_kd = link_kd + serp_kd + content_kd
        competitor_total_kds.append(total_kd)

        breakdown_details.append({
            "domain": comp["domain"],
            "link_kd": round(link_kd * 100, 2),
            "serp_kd": round(serp_kd * 100, 2),
            "content_kd": round(content_kd * 100, 2),
            "total_kd": round(total_kd * 100, 2)
        })

    # Final KD = median of total_kds
    final_kd = statistics.median(competitor_total_kds) * 100 if competitor_total_kds else 0

    # Apply SERP-level context modifier (± KD points)
    # cont_modifier = context_modifier(competitors, wrext_data["serp_normalized"], keyword_intent)

    # final_kd = final_kd + cont_modifier

    # Clamp final KD
    final_kd = max(0, min(final_kd, 100))


    # Notes
    notes = []
    brands = {"brand", "publisher", "gov", "edu"}
    brand_count = sum(1 for c in competitors if wrext_data["serp_normalized"]["domain_stats"].get(c["domain"], {}).get("type") in brands)
    if brand_count >= len(competitors) * 0.5:
        notes.append("High brand dominance")

    return {
        "keyword": keyword,
        "kd": round(final_kd, 2),
        "breakdown": {
            "competitor_details": breakdown_details
        },
        "notes": notes
    }


def compute_keyword_difficulty(wrext_data: WREXT, keyword_intent: str = "informational") -> dict:

    store = 0
    intent_input = []
    dicts = { 'INFORMATIONAL' :0, 'COMMERCIAL' :0, 'TRANSACTIONAL' :0, 'NAVIGATIONAL' :0}


    for competitor in wrext_data["competitors"]:
        intent_input.append(competitor['intent_distribution'])

    for intent_distribution in intent_input:
        for key,value in intent_distribution.items():
            if value!=0:
                dicts[key] = dicts[key] + 1

    for key,value in dicts.items():
        if value>store:
            max_key= key
            store = value
            keyword_intent = max_key


    keyword = wrext_data["serp_normalized"]["query"]
    # Default intent to informational if not found
    keyword_intent = (wrext_data.get("seo_result") or {}).get("intent", {}).get("primary_intent", "informational")





    kd_result = calculate_final_kd(keyword=keyword, keyword_intent=keyword_intent, wrext_data=wrext_data)

    return {
        "seo_result": {
            "keyword_difficulty2": kd_result
        }
    }
