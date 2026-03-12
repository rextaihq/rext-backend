import logging
from datetime import datetime
from typing import Dict, Any, Literal
from src.flow.states.rext import REXT
from langgraph.types import interrupt, Command
from langgraph.graph import END

from src.flow.utils.intent_utils import get_consensus_intent, calculate_intent_with_llm, get_intent_consensus

logger = logging.getLogger(__name__)


async def keyword_recommendation(state: REXT, config, *, runtime) -> Dict[str, Any] | Command:
    """
    Enhanced LangGraph node: Google-like keyword recommendations.
    Stores each run with a unique key to preserve history.
    """

    serp_normalized = state.get("serp_normalized")
    competitors = state.get("competitors", [])
    seo_result = state.get("seo_result", {})
    serp_backlinks = seo_result.get("serp_backlinks", {})

    recommendations = serp_normalized.get("related_topics", []) if serp_normalized else []
    
    # Use consensus intent (API + Competitors + LLM) for better accuracy
    serp_payload = state.get("serp_payload")
    query = serp_payload.get("query", "") if serp_payload else ""
    organic_results = serp_normalized.get("normalize_results", []) if serp_normalized else []
    
    api_intent = serp_backlinks.get("main_intent")
    
    # Calculate SERP intent (Consensus among competitors)
    serp_intent, serp_confidence = get_consensus_intent(api_intent, competitors)
    
    # Calculate LLM intent
    llm_predicted = await calculate_intent_with_llm(query, organic_results)
    
    # Get final consensus
    intent_analysis = get_intent_consensus(api_intent, serp_intent, serp_confidence, llm_predicted)
    search_intent = intent_analysis["consensus_intent"]
    
    volume = serp_backlinks.get("search_volume", 0)
    keyword_difficulty = serp_backlinks.get("keyword_difficulty", 0)
    backlinks = serp_backlinks.get("backlinks", 0)
    referring_domains = serp_backlinks.get("referring_domains", 0)

    serp_payload = state.get("serp_payload")
    store = runtime.store
    user_id = serp_payload.get("user_id") if serp_payload else None
    workspace_id = serp_payload.get("workspace_id") if serp_payload else None

    print(f"   user_id: {user_id}")
    print(f"   workspace_id: {workspace_id}")

    if not user_id or not workspace_id:
        print("❌ Missing user_id or workspace_id")
        return {"seo_result": seo_result}

    # Structured namespace for privacy and better search via prefix
    namespace = ("library", str(user_id), str(workspace_id))
    print(f"   namespace: {namespace}")

    original_query = serp_payload.get("query", "") if serp_payload else ""

    print(f"   original_query: {original_query}")
    print(f"   recommendations: {recommendations}")

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
                    "error": "No SERP data available",
                },
            }
        }

    # ✅ CREATE UNIQUE KEY FOR EACH RUN
    # Use timestamp + query to create unique keys
    timestamp = datetime.now().isoformat()
    unique_key = f"library_{original_query}_{timestamp}"

    # Store the data
    try:
        # Enrich data with organic results and questions for better recommendation context
        top_organic = []
        if serp_normalized and serp_normalized.get("normalize_results"):
            # Store top 10 results with essential info
            for res in serp_normalized.get("normalize_results", [])[:10]:
                top_organic.append(
                    {
                        "title": res.get("title"),
                        "url": res.get("url"),
                        "snippet": res.get("snippet"),
                        "position": res.get("position"),
                    }
                )

        data_to_store = {
            "original_query": original_query,
            "recommendations": recommendations,
            "questions": serp_normalized.get("questions", []) if serp_normalized else [],
            "related_topics": serp_normalized.get("related_topics", []) if serp_normalized else [],
            "top_organic_results": top_organic,
            "seo_state": {
                "keyword_difficulty": keyword_difficulty,
                "intent": search_intent or "informational",
                "volume": volume,
                "backlinks": backlinks,
                "referring_domains": referring_domains,
            },
            "timestamp": timestamp,  # Include timestamp in value
        }

        # Store with unique key (keeps history)
        await store.aput(
            namespace=namespace,
            key=unique_key,
            value=data_to_store,
        )
        print(f"✅ Stored with unique key: {unique_key}")

    except Exception as e:
        logger.exception(f"Store error: {e}")
        print(f"❌ Store error: {e}")
        return {"seo_result": seo_result}

    # Interrupt for user selection
    user_selection = interrupt(
        {
            "instruction": "Select a keyword for your content",
            "type": "keyword Selection",
            "Primary Keyword": original_query,
            "Recommendations": recommendations,
            "seo_state": {
                "keyword_difficulty": keyword_difficulty,
                "intent": search_intent or "informational",
                "volume": volume,
                "backlinks": backlinks,
                "referring_domains": referring_domains,
            },
        }
    )

    # Extract primary keyword
    primary_keyword = (
        user_selection.strip()
        if isinstance(user_selection, str)
        else user_selection.get("Primary Keyword", "").strip()
        if isinstance(user_selection, dict)
        else original_query
    )

    # Check if keyword changed
    is_changed = primary_keyword.lower() != original_query.lower()

    return {
        "seo_result": {
            **seo_result,
            "serp_backlinks": {
                **serp_backlinks,
                "main_intent": search_intent or serp_backlinks.get("main_intent", "unknown")
            },
            "keyword_recommendations": {
                "original_title": original_query,
                "selected_keyword": primary_keyword,
                "recommendations": recommendations,
                "error": None,
                "is_changed": is_changed,
            },
        },
        "serp_payload": {
            **serp_payload,
            "query": primary_keyword,
        },
    }