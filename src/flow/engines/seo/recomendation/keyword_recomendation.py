from typing import Dict, Any, Literal
from src.flow.states.wrext import WREXT
from src.services.keyword_service import KeywordExtractor
from langgraph.types import interrupt, Command
from langgraph.graph import END

def keyword_recommendation(state: WREXT) -> Dict[str, Any] | Command:
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

    competitors = state.get("competitors", [])
    
    # Calculate dominant intent from competitors
    intent_aggregation = {}
    for competitor in competitors:
        intent_dist = competitor.get("intent_distribution", {})
        for intent_type, count in intent_dist.items():
            if intent_type not in intent_aggregation:
                intent_aggregation[intent_type] = []
            intent_aggregation[intent_type].append(count)
    
    # Calculate mean for each intent and find the one with highest mean
    dominant_intent = None
    max_mean = 0
    
    if intent_aggregation:
        for intent_type, counts in intent_aggregation.items():
            mean_count = sum(counts) / len(counts)
            if mean_count > max_mean:
                max_mean = mean_count
                dominant_intent = intent_type
        
        print(f"📊 Intent Analysis:")
        for intent_type, counts in intent_aggregation.items():
            mean_val = sum(counts) / len(counts)
            print(f"   - {intent_type}: mean={mean_val:.2f}, occurrences={len(counts)}")
        print(f"🎯 Dominant Intent: {dominant_intent} (mean={max_mean:.2f})")
    
    # Scrape Data from SERP
    original_query = serp_normalized.get("query", "") if serp_normalized else ""
    print(f"🔍 Original Query: {original_query}")
    
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
    
    # From relevance_keyword_finder node
    extracted_keywords = seo_result.get("extracted_keywords", {}).get("all", [])
    
    # From compute_keyword_difficulty node
    keyword_difficulty = seo_result.get("keyword_difficulty", {})
    
    # From seo_opportunity_node
    seo_opportunity = seo_result.get("seo_opportunity", {})
    
    # From competitors_gap_node
    competitors_gap = seo_result.get("content_gaps", {})
    
    print(f"📊 SEO Data Collected:")
    print(f"   - Keywords extracted: {len(extracted_keywords)}")
    print(f"   - Difficulty level: {keyword_difficulty.get('difficulty_level', 'N/A')}")
    print(f"   - Opportunity score: {seo_opportunity.get('opportunity_score', 'N/A')}")
    print(f"   - Content gaps: {len(competitors_gap.get('missing_topics', []))} missing topics")
    
    # ==================================
    # GENERATE SMART RECOMMENDATIONS
    # ==================================
    extractor = KeywordExtractor()
    title_result = extractor.keyword_recommendation(
        serp_normalized=serp_normalized,
        extracted_keywords=extracted_keywords,
        seo_opportunity=seo_opportunity,
        competitors_gap=competitors_gap,
        keyword_difficulty=keyword_difficulty,
        top_n=10
    )
    
    # ==================================
    # PREPARE RICH INTERRUPT DATA
    # ==================================
    recommendations = title_result.get("recommendations", [])
    seo_context = title_result.get("seo_context", {})
    
    # Extract just the keywords for user selection
    keyword_options = [rec.get("keyword") for rec in recommendations if rec.get("keyword")]
    
    # Interrupt for user selection - simple keyword list
    user_selection = interrupt({
        "instruction": "Select a keyword for your content",
        "type": "keyword Selection",
        "Primary Keyword": original_query,
        "Recommendations": keyword_options,
        "seo_state": {
            # Full KeywordDifficultyState object
            "keyword_difficulty": keyword_difficulty.get("kd", {}),
            "intent": dominant_intent if dominant_intent else "informational",
            "volume": "50"  
        }
    })
    
    # Safely extract primary keyword (handles str|dict|fallback)
    primary_keyword = (
        user_selection.strip() if isinstance(user_selection, str)
        else user_selection.get("Primary Keyword", "").strip() if isinstance(user_selection, dict)
        else original_query
    )
    print(f"✅ User Selection: {primary_keyword}")
    
    # ==================================
    # ROUTE BASED ON KEYWORD SELECTION
    # ==================================
    if primary_keyword.lower() == original_query.lower():
        print("➡️ Original keyword selected - continuing to content engine")
        return {
            "seo_result":{
                **seo_result,
                "keyword_recommendations": {
                    "original_title": original_query,
                    "selected_keyword": primary_keyword,
                    "recommendations": recommendations,
                    "patterns_found": title_result.get("patterns_found", {}),
                    "seo_context": seo_context,
                    "top_keywords_used": title_result.get("top_keywords_used", []),
                    "total_competitors_analyzed": title_result.get("total_competitors_analyzed", 0),
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
        print(f"🔄 New keyword selected: '{primary_keyword}' - re-running SEO analysis")
        # New keyword → Restart SEO engine to regenerate recommendations

        return {
            "seo_result":{
                **seo_result,
                "keyword_recommendations": {
                    "original_title": original_query,
                    "selected_keyword": primary_keyword,
                    "recommendations": recommendations,
                    "patterns_found": title_result.get("patterns_found", {}),
                    "seo_context": seo_context,
                    "top_keywords_used": title_result.get("top_keywords_used", []),
                    "total_competitors_analyzed": title_result.get("total_competitors_analyzed", 0),
                    "error": None,
                    "is_changed": True
                }
            },
            "serp_normalized": {
                **serp_normalized,
                "query": primary_keyword 
            }
        }