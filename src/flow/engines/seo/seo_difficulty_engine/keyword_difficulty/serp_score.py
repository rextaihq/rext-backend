from src.flow.states.wrext import SERPNORMALIZED, Competitor
from datetime import datetime

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
            return 0.10
        else:
            return 0.1
        
    except:
        return 0.3
    

ugc_keywords = ["reddit.com", "quora.com", "stackexchange.com", "stackoverflow.com"]

def clamp(val, min_v=0, max_v=100):
    return max(min(val, max_v), min_v)


def serp_saturation_score(serp_normalized: SERPNORMALIZED, competitors: list[Competitor]) -> dict:

    """
    Compute SERP saturation score with freshness adjustment.
    """
    score = 0

    # Featured Snippet
    featured_snippet = any(c.get("featured_snippet", False) for c in competitors)
    if featured_snippet:
        score += 5

    # People also ask (PAA)
    # paa_present = len(serp_normalized.get("questions", [])) > 0
    paa_present = serp_normalized.get("features", {}).get('people_also_ask', False) or len(serp_normalized.get("questions", [])) > 0
    if paa_present:
        score += 3

    '''
    # Top Stories
    top_stories_present = serp_normalized.get("features", {}).get("top_stories", False)
    if top_stories_present:
        score += 6
    '''

    # Ads (top)
    '''
    ads_top_present = serp_normalized.get("features", {}).get("ads_top", False)
    if ads_top_present:
        score += 4
    '''


    # Sitelinks present
    sitelinks_present = any(c.get("has_sitelinks", False) for c in competitors)
    if sitelinks_present:
        score += 4

    # --- Freshness adjustment ---
    # Increase score slightly if top competitors are recent
    # recent_count = sum(1 for c in competitors if c.get("freshness", {}).get("recent", 0) > 0)
    normalized_result = serp_normalized["normalize_results"]

    scores = [
    normalize_freshness(res.get("date"))
    for res in normalized_result
    ]
    freshness_score = sum(scores) / len(normalized_result)

    # freshness_score = normalize_freshness(normalized_result.get("date"))
    if freshness_score >= 0.85:
        score += 2

    # freshness_boost = (recent_count / max(len(competitors), 1)) * 2  # max +2 points
    # score += freshness_boost

    # Clamp and normalize 0-100 (max raw score = 25 + 2 freshness)
    normalized_score = clamp(score / 27 * 100, 0, 100)

    return {
        "serp_saturation_score": round(normalized_score, 2),
        "details": {
            "featured_snippet": 5 if featured_snippet else 0,
            "paa": 3 if paa_present else 0,
            # "top_stories": 6 if top_stories_present else 0,
            # "ads_top": 4 if ads_top_present else 0,
            # "forums_dominance": 3 if forums_dominance else 0,
            "sitelinks_present": 4 if sitelinks_present else 0,
            # "freshness_boost": round(freshness_boost, 2)
        }
    }
