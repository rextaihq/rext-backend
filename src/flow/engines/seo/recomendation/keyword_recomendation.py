import logging
from datetime import datetime
from typing import Any, Dict

from langgraph.types import Command, interrupt

from src.flow.states.rext import REXT
from src.flow.utils.intent_utils import get_serp_intents_from_competitors

logger = logging.getLogger(__name__)


async def keyword_recommendation(state: REXT, config, *, runtime) -> Dict[str, Any] | Command:
    """
    Enhanced LangGraph node: Google-like keyword recommendations.
    Stores each run with a unique key to preserve history.
    """

    serp_normalized = state.get("serp_normalized")
    seo_result = state.get("seo_result", {})
    serp_backlinks = seo_result.get("serp_backlinks", {})
    competitors = state.get("competitors", [])

    recommendations = serp_normalized.get("related_topics", []) if serp_normalized else []

    # Intent is derived from SERP competitor distribution only.
    serp_intent = get_serp_intents_from_competitors(competitors)
    search_intent = serp_intent["main_intent"]
    foreign_intent = serp_intent["foreign_intent"]

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
        print("Missing user_id or workspace_id")
        return {"seo_result": seo_result}

    namespace = ("library", str(user_id), str(workspace_id))
    print(f"   namespace: {namespace}")

    original_query = serp_payload.get("query", "") if serp_payload else ""

    print(f"   original_query: {original_query}")
    print(f"   recommendations: {recommendations}")

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

    timestamp = datetime.now().isoformat()
    unique_key = f"library_{original_query}_{timestamp}"

    try:
        top_organic = []
        if serp_normalized and serp_normalized.get("normalize_results"):
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
                "foreign_intent": foreign_intent or "informational",
                "volume": volume,
                "backlinks": backlinks,
                "referring_domains": referring_domains,
            },
            "timestamp": timestamp,
        }

        await store.aput(
            namespace=namespace,
            key=unique_key,
            value=data_to_store,
        )
        print(f"Stored with unique key: {unique_key}")

    except Exception as e:
        logger.exception("Store error: %s", e)
        print(f"Store error: {e}")
        return {"seo_result": seo_result}

    user_selection = interrupt(
        {
            "instruction": "Select a keyword for your content",
            "type": "keyword Selection",
            "Primary Keyword": original_query,
            "Recommendations": recommendations,
            "seo_state": {
                "keyword_difficulty": keyword_difficulty,
                "intent": search_intent or "informational",
                "foreign_intent": foreign_intent or "informational",
                "volume": volume,
                "backlinks": backlinks,
                "referring_domains": referring_domains,
            },
        }
    )

    primary_keyword = (
        user_selection.strip()
        if isinstance(user_selection, str)
        else user_selection.get("Primary Keyword", "").strip()
        if isinstance(user_selection, dict)
        else original_query
    )

    is_changed = primary_keyword.lower() != original_query.lower()

    if "serp_backlinks" in seo_result:
        seo_result["serp_backlinks"]["main_intent"] = search_intent
        seo_result["serp_backlinks"]["foreign_intent"] = foreign_intent

    return {
        "seo_result": {
            **seo_result,
            "keyword_recommendations": {
                "original_title": original_query,
                "selected_keyword": primary_keyword,
                "recommendations": recommendations,
                "error": None,
                "is_changed": is_changed,
                "library_key": unique_key,
            },
        },
        "serp_payload": {
            **serp_payload,
            "query": primary_keyword,
        },
    }
