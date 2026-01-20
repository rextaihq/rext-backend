from typing import Dict
from langchain_core.documents import Document
from src.flow.states.wrext import WREXT
from src.flow.states.seo_state import SEORESULT
from src.flow.engines.seo.dataforseo_response import get_dataforseo_data

def keyword_difficulty_node(state: WREXT) -> Dict[str, SEORESULT]:
    serp = state.get("serp_normalized", {})
    competitors = state.get("competitors", [])
    documents = (state.get("scrape_context") or {}).get("documents", [])
    keyword = (state.get("serp_payload") or {}).get("query", "").lower()
    results = serp.get("normalize_results", [])[:10]
    normalized_results = serp.get("normalize_results", [])

    dataforseo_data = get_dataforseo_data(serp.get("query"))

    dataforseo_data.get("images")

    # 1. LINK DIFFICULTY (PROXY) – 0–20
    images = dataforseo_data.get("images")
    videos = dataforseo_data.get("videos")
    backlinks = dataforseo_data.get("backlinks")
    referring_domains = dataforseo_data.get("referring_domains")
    # main_domain_rank = 0
    # rank = 0
    # referring_page = 0
    dofollow_links = dataforseo_data.get("dofollow_links")
    link_score = 0
    # sitelink_ratio = sum(1 for c in competitors if c.get("has_sitelinks")) / max(1, len(competitors))
    # if sitelink_ratio >= 0.3:
    #     link_score += 10
    # elif sitelink_ratio >= 0.2:
    #     link_score += 5
    # else:
    #     link_score += 0

    # # Featured snippet ownership
    # fs_ratio = sum(1 for c in competitors if c.get("featured_snippet")) / max(1, len(competitors))
    # if fs_ratio >= 0.3:
    #     link_score += 10
    # elif fs_ratio >= 0.15:
    #     link_score += 5
    # else:
    #     link_score += 0

    # link_difficulty = min(20, link_score)

    if backlinks >= 5000:
        link_score += 20
    elif backlinks >= 3500:
        link_score += 10
    elif backlinks >= 2500:
        link_score += 5
    else:
        link_score += 0

    if referring_domains >= 1000:
        link_score += 15
    elif referring_domains >= 600:
        link_score += 7
    else:
        link_score += 0

    if dofollow_links >= 5000:
        link_score += 15
    elif dofollow_links >= 2500:
        link_score += 7
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


    # 3. AUTHORITY PRESSURE – 0–5
    # authority_pressure = 0
    # for c in competitors:
    #     for pos in c.get("top_positions", []):
    #         if pos <= 5:
    #             authority_pressure += 1

    # avg_snippet_length = sum(c.get("avg_snippet_length", 0) for c in competitors) / max(1, len(competitors))
    # if avg_snippet_length >= 130 and avg_snippet_length <= 200:
    #     authority_pressure += 4

    # content = []

    # for d in documents:
    #     doc = d.get("document")

    #     if isinstance(doc, Document) and doc.page_content.strip():
    #         page_content = doc.page_content.split("\n")
    #         content.append(page_content)
    #         break  

    # avg_content = (
    #     sum(d.get("content_length", 0) for d in documents) / len(documents)
    #     if documents else 0
    # )

    # avg_headings = (
    #     sum(len(d.get("headings", [])) for d in documents) / len(documents)
    #     if documents else 0
    # )
    # if avg_content >= 35000:
    #     authority_pressure += 6
    # elif avg_content >= 20000:
    #     authority_pressure += 3

    # if avg_headings >= 35:
    #     authority_pressure += 4
    # elif avg_headings >= 23:
    #     authority_pressure += 2

    # authority_pressure = min(5, authority_pressure)

    # 4. SERP FEATURE DENSITY – 0–6
    features = serp.get("features", {})
    feature_pressure = 0
    feature_pressure += 3 if features.get("people_also_ask") else 0
    feature_pressure += min(3, len(serp.get("questions", [])))

    serp_feature_pressure = min(6, feature_pressure)

    # 5. FRESHNESS PRESSURE – 0–5
    recent_ratio = sum(
        1 for c in competitors if c.get("freshness", {}).get("recent") == 1
    ) / max(1, len(competitors))

    if recent_ratio >= 0.8:
        freshness_pressure = 5
    elif recent_ratio >= 0.5:
        freshness_pressure = 2
    else:
        freshness_pressure = 0

    # # 6. INTENT LOCK – 0–10
    # intent_counts = {}
    # for c in competitors:
    #     for i, v in c.get("intent_distribution", {}).items():
    #         if v > 0:
    #             intent_counts[i] = intent_counts.get(i, 0) + 1

    # if intent_counts:
    #     intent_ratio = max(intent_counts.values()) / max(1, len(competitors))
    #     intent_lock = 10 if intent_ratio >= 0.8 else 5 if intent_ratio >= 0.5 else 0

    # 7. ON-PAGE SATURATION – 0–9
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

    # 8. BRAND DOMINANCE – 0–15
    brand_ratio = sum(1 for c in competitors if c.get("is_brand")) / max(1, len(competitors))
    brand_dominance = 15 if brand_ratio >= 0.8 else 7 if brand_ratio >= 0.4 else 0

    # FINAL SCORE (Normalize to 100)
    raw_score = (
        link_difficulty
        # + domain_monopoly
        # + authority_pressure
        + serp_feature_pressure
        + freshness_pressure
        # + intent_lock
        + onpage_pressure
        + brand_dominance
    )

    if images:
        raw_score -= 5
    if videos:
        raw_score -= 5

    score = min(100, raw_score)

    if score >= 75:
        level = "very_hard"
    elif score >= 55:
        level = "hard"
    elif score >= 35:
        level = "medium"
    else:
        level = "easy"

    return {
        "seo_result": {
            "keyword_difficulty": {
                "keyword": keyword,
                "difficulty_score": score,
                "difficulty_level": level,
                "difficulty_signals": {
                    "link_difficulty": link_difficulty,
                    # "domain_monopoly": domain_monopoly,
                    # "authority_pressure": authority_pressure,
                    "serp_feature_pressure": serp_feature_pressure,
                    "freshness_pressure": freshness_pressure,
                    # "intent_lock": intent_lock,
                    "onpage_pressure": onpage_pressure,
                    "brand_dominance": brand_dominance,
                    # "dataforseo_response":dataforseo_data,
                    # "monopoly_ratio": monopoly_ratio,
                    # "fs_ratio": fs_ratio,
                    # "sitelink_ratio": sitelink_ratio,
                    # "avg_snippet_length": avg_snippet_length,
                    # "avg_headings": avg_headings,
                    # "recent_ratio": recent_ratio,
                    # "url_ratio": url_ratio,
                    # "intitle_ratio": intitle_ratio,
                    # "brand_ratio": brand_ratio,
                    # "intent_ratio": intent_ratio,
                    # "avg_title_length": avg_title_length,
                    # "content": content,
                },
            }
        }
    }