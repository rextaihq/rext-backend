import math
import statistics
from datetime import datetime
from src.flow.states.wrext import Competitor, NormalizedOrganicResult, ScrapeContext
from typing import List
def clamp(val, min_v=0, max_v=1):
    return max(min(val, max_v), min_v)

'''
clamp(1.5)     # → 1
clamp(-0.3)    # → 0
clamp(0.6)     # → 0.6
clamp(75, 0, 100)  # → 75
clamp(120, 0, 100) # → 100
'''

def normalize_word_count(wc, max_wc=2000):
    """Assume max deep content ~2000 words"""
    return clamp(wc / max_wc)

def normalize_structure(h2_count, h3_count, max_h2=10, max_h3=20):
    return clamp((h2_count/max_h2 * 0.6 + h3_count/max_h3 * 0.4))

def normalize_freshness(date_str):
    if not date_str:
        return 0.3  # unknown freshness

    try:
        dt = datetime.fromisoformat(date_str)
        days = (datetime.now() - dt).days

        if days <= 30:
            return 1.0
        elif days <= 180:
            return 0.85
        elif days <= 365:
            return 0.7
        elif days <= 730:
            return 0.5
        elif days <= 1095:
            return 0.3
        else:
            return 0.1
        
    except:
        return 0.3


def intent_match(keyword_intent, page_intent):
    """
    keyword_intent: 'informational', 'commercial', etc.
    page_intent: dict from competitor intent_distribution
    """
    if not page_intent:
        return 0.5  # unknown
    total = sum(page_intent.values())
    if total == 0:
        return 0.5
    page_score = page_intent.get(keyword_intent, 0) / total
    return clamp(page_score)

    """
    page_intent
    {
    "informational": 7,
    "commercial": 1,
    "transactional": 0
    }

    """

def content_strength(keyword_intent: str, competitor: Competitor, normalized_result: NormalizedOrganicResult, scrape_data: ScrapeContext) -> float:
    # Word count proxy
    wc = sum(d["content_length"] for d in scrape_data["documents"]) / len(scrape_data["documents"])
    wc_score = normalize_word_count(wc)

    # i need to extrat heading for each article and then count heading and give score to each article and finally tack the avg count of heading.

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
    # depth / structure 40%, freshness 20%, intent 40%
    strength = 0.4 * (wc_score + avg_struct_score)/2 + 0.2 * freshness_score + 0.4 * intent_score
    return clamp(strength)


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
