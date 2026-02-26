from PIL.Image import logger
from typing import Dict, Any, Literal
from src.flow.states.rext import REXT
from langgraph.types import interrupt, Command
from langgraph.graph import END

def keyword_recommendation(state: REXT) -> Dict[str, Any] | Command:
    """
    Enhanced LangGraph node: Google-like keyword recommendations.
    
    Utilizes ALL SEO signals from parallel nodes:
    - keyword_difficulty: Difficulty scores and breakdown
    - competitors_gap: Missing topics and questions
    - seo_opportunity: Opportunity scores and strategy
    - extracted_keywords: TF-IDF ranked keywords
    
    Flow:
    1. Collect all SEO data from parallel nodes
    2. Generate intelligent recommendations using keyword_recommendation service
    3. interrupt() for user selection with rich context
    4. If original keyword → END (continue to content_engine)
    5. If new keyword → Restart from serp_engine with new query
    """
    serp_normalized = state.get("serp_normalized")
    seo_result = state.get("seo_result", {})
    serp_backlinks = seo_result.get("serp_backlinks", {})
    logger.info("serp_backlinks", serp_backlinks)

    recommendations = serp_normalized.get("related_topics", [])
    seach_intent = serp_backlinks.get("main_intent")
    volume = serp_backlinks.get("search_volume")
    keyword_difficulty = serp_backlinks.get("keyword_difficulty")
    backlinks = serp_backlinks.get("backlinks")
    referring_domains = serp_backlinks.get("referring_domains")

    competitors = state.get("competitors", [])
    
    # Scrape Data from SERP
    original_query = serp_normalized.get("query", "") if serp_normalized else ""
    
    # Early return if no SERP data
    if not serp_normalized:
        return {
            "seo_result": {
                **seo_result,
                "keyword_recommendations": {
                    "original_title": "",
                    "recommendations": [],
                    "patterns_found": {},
                    "seo_context": {},
                    "top_keywords_used": [],
                    "total_competitors_analyzed": 0,
                    "error": "No SERP data available"
                }
            }
        }
    
    # Interrupt for user selection - simple keyword list
    user_selection = interrupt({
        "instruction": "Select a keyword for your content",
        "type": "keyword Selection",
        "Primary Keyword": original_query,
        "Recommendations": recommendations,
        "seo_state": {
            # Full KeywordDifficultyState object
            "keyword_difficulty": keyword_difficulty,
            "intent": seach_intent if seach_intent else "informational",
            "volume": volume,  
            "backlinks": backlinks,
            "referring_domains": referring_domains
        }
    })
    
    # Safely extract primary keyword (handles str|dict|fallback)
    primary_keyword = (
        user_selection.strip() if isinstance(user_selection, str)
        else user_selection.get("Primary Keyword", "").strip() if isinstance(user_selection, dict)
        else original_query
    )
    
    # ==================================
    # ROUTE BASED ON KEYWORD SELECTION
    # ==================================
    if primary_keyword.lower() == original_query.lower():
        return {
            "seo_result":{
                **seo_result,
                "keyword_recommendations": {
                    "original_title": original_query,
                    "selected_keyword": primary_keyword,
                    "recommendations": recommendations,
                    "error": None,
                    "is_changed": False
                }
            },
            "serp_normalized": {
                **serp_normalized,
                "query": primary_keyword  # Update query for new SEO analysis
            }
        }

    else:
        return {
            "seo_result":{
                **seo_result,
                "keyword_recommendations": {
                    "original_title": original_query,
                    "selected_keyword": primary_keyword,
                    "recommendations": recommendations,
                    "error": None,
                    "is_changed": True,
                }
            },
            "serp_normalized": {
                **serp_normalized,
                "query": primary_keyword 
            }
        }