from typing import Dict, Any
from src.flow.states.wrext import WREXT
from src.services.seo_service import KeywordExtractor
from langgraph.types import interrupt, Command
from langgraph.graph import END

def recommendation(state: WREXT) -> Dict[str, Any]:
    """
    LangGraph node: Generate title recommendations based on SERP analysis.
    
    Uses competitor title patterns and extracted keywords to suggest
    optimized titles for the user's content.
    """
    serp_normalized = state.get("serp_normalized")
    seo_result = state.get("seo_result", {})
    
    if not serp_normalized:
        return {
            "seo_result": {
                **seo_result,
                "title_recommendations": {
                    "original_title": "",
                    "recommendations": [],
                    "patterns_found": {},
                    "top_keywords_used": [],
                    "total_competitors_analyzed": 0,
                    "error": "No SERP data available"
                }
            }
        }
    
    # Get data from state
    query = serp_normalized.get("query", "")
    normalize_results = serp_normalized.get("normalize_results", [])
    related_topics = serp_normalized.get("related_topics", [])
    
    # Get extracted keywords if available
    extracted_keywords = seo_result.get("extracted_keywords", {}).get("all", [])
    
    # Initialize extractor and generate recommendations
    extractor = KeywordExtractor()
    title_result = extractor.title_recommendation(
        user_title=query,
        normalize_results=normalize_results,
        related_topics=related_topics,
        extracted_keywords=extracted_keywords,
        top_n=5
    )
    
    # recomendation
    user_selection = interrupt({
        "instruction": "Select a title for your content",
        "Primary Keyword": title_result.get("original_title", ""),
        "Related Keywords": [data.get("title") for data in title_result.get("recommendations", [])],
    })

    if user_selection:
        # Handle both string and dictionary responses from interrupt
        if isinstance(user_selection, str):
            # If user_selection is a string, treat it as the primary keyword
            primary_keyword = user_selection
            related_keywords = title_result.get("recommendations", [])
        elif isinstance(user_selection, dict):
            # If it's a dictionary, extract the values
            primary_keyword = user_selection.get("Primary Keyword", "")
            related_keywords = user_selection.get("Related Keywords", [])
        else:
            # Fallback to original values if unexpected type
            primary_keyword = title_result.get("original_title", "")
            related_keywords = title_result.get("recommendations", [])
        
        return Command(
            update={
                "seo_result": {
                    **seo_result,
                    "title_recommendations": {
                        "original_title": primary_keyword,
                        "recommendations": related_keywords,
                        "patterns_found": title_result.get("patterns_found", {}),
                        "top_keywords_used": title_result.get("top_keywords_used", []),
                        "total_competitors_analyzed": title_result.get("total_competitors_analyzed", 0),
                        "error": None
                    }
                },
                "serp_payload": {
                    "query": primary_keyword if isinstance(primary_keyword, str) else "",
                    "country": state.get("serp_payload", {}).get("country", "us")
                }
            },
            goto=END 
        )
