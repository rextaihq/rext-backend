import statistics
from src.flow.states.wrext import Competitor, NormalizedOrganicResult, ScrapeContext
from typing import List
from src.flow.engines.seo.seo_difficulty_engine.utils.utils import clamp, normalize_freshness
    

def normalize_word_count(wc, max_wc=2000):
    """Assume max deep content ~2000 words"""
    return clamp(wc / max_wc)


def normalize_structure(h2_count, h3_count, max_h2=10, max_h3=20):
    return clamp((h2_count/max_h2 * 0.6 + h3_count/max_h3 * 0.4))


def intent_match(keyword_intent, page_intent):
    """
    keyword_intent: 'informational', 'commercial', etc.
    page_intent: dict from competitor intent_distribution
    """

    """
    page_intent
    {
    "informational": 7,
    "commercial": 1,
    "transactional": 0
    }

    """

    if not page_intent:
        return 0.5  # unknown
    total = sum(page_intent.values())
    if total == 0:
        return 0.5
    

    page_score = page_intent.get(keyword_intent, 0) / total
    return clamp(page_score)



def content_strength(keyword_intent: str, competitor: Competitor, normalized_result: NormalizedOrganicResult, scrape_data: ScrapeContext) -> float:
    # Word count proxy
    wc = sum(d["content_length"] for d in scrape_data["documents"]) / len(scrape_data["documents"])
    wc_score = normalize_word_count(wc)
    
    # Content structure proxy
    # if no headings, approximate: snippet length => structure \
    # # Match lines starting with #, ##, ###, etc.
    h2_counts = []
    h3_counts = []

    for doc in scrape_data["documents"]:
        headings = doc.get("headings", [])

        h2_counts.append(
            sum(1 for h in headings if h.startswith("##") and not h.startswith("###"))
        )

        h3_counts.append(
            sum(1 for h in headings if h.startswith("###") and not h.startswith("####"))
        )



    article_struct_scores = []

    for h2, h3 in zip(h2_counts, h3_counts):
        score = normalize_structure(h2, h3)
        article_struct_scores.append(score)

    avg_struct_score = (
    sum(article_struct_scores) / len(article_struct_scores)
    if article_struct_scores else 0
    )

    # Freshness
    # scores = [
    # normalize_freshness(res.get("date"))
    # for res in normalized_result
    # ]

    # freshness_score = sum(scores) / len(normalized_result)
    freshness_score = normalize_freshness(normalized_result.get("date"))

    # Intent match
    intent_score = intent_match(keyword_intent, competitor.get("intent_distribution", {}))

    # Weighted aggregation (example weights)
    # depth / structure 30%, freshness 30%, intent 40%
    strength = 0.3 * (wc_score + avg_struct_score)/2 + 0.3 * freshness_score + 0.4 * intent_score
    return clamp(strength)

'''
def content_difficulty_score(keyword_intent: str, normalized_results: List[NormalizedOrganicResult], competitors: list[Competitor], scrape_context: ScrapeContext) -> dict:
    strengths = []
    for c in competitors:
        # Find the corresponding normalized result for this competitor
        nr = next(
            (res for res in normalized_results if res['domain'] == c['domain'] and res['position'] in c['top_positions']),
            None
        )
        if nr:
            strengths.append(content_strength(keyword_intent, c, nr,scrape_context))

    median_strength = statistics.median(strengths) if strengths else 0
    content_score = round(median_strength * 100, 2)

    return {
        "content_difficulty_score": content_score,
        "details": {
            "median_strength": round(median_strength, 3),
            "num_pages": len(strengths)
        }
    }
'''

