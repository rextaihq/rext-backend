import requests
import json
import os
import logging
from dotenv import load_dotenv
from typing import Dict, Any, List
from src.flow.states.rext import REXT
import httpx
from src.flow.states.countries import VALID_COUNTRY_CODES
from src.flow.states.seo_state import SERPBacklinks

load_dotenv()

logger = logging.getLogger(__name__)

DATAFORSEO_BACKLINKS_URL = os.getenv("DATAFORSEO_BACKLINKS_URL")
AUTH_HEADER = os.getenv("DATAFORSEO_AUTH_HEADER")

if not DATAFORSEO_BACKLINKS_URL or not AUTH_HEADER:
    raise EnvironmentError("Missing DataForSEO environment variables")

headers = {
    "Authorization": f"Basic {AUTH_HEADER}",
    "Content-Type": "application/json"
}

# =========================
# 🚀 MAIN FUNCTION (SINGLE KEYWORD)
# =========================
async def get_dataforseo_data(
    keyword: str,
    location_name: str = "United States",
    language_code: str = "en",
    include_serp_info: bool = True
) -> Dict:

    payload = [{
        "location_name": location_name,
        "language_code": language_code,
        "keyword": keyword,   # ✅ keyword suggestions uses singular 'keyword'
        "include_serp_info": include_serp_info,
        "include_seed_keyword": True
    }]

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(DATAFORSEO_BACKLINKS_URL, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()

            tasks = data.get("tasks", [])
            if not tasks:
                return {}
            
            result = tasks[0].get("result")
            if not result or not result[0]:
                return {}
                
            # ✅ Metrics for the actual keyword are in 'seed_keyword_data'
            # when using keyword_suggestions with include_seed_keyword: True
            item = result[0].get("seed_keyword_data", {})
            if not item:
                # Fallback to first item if seed_keyword_data is missing
                items = result[0].get("items", [])
                if items:
                    item = items[0]
                else:
                    return {}

            backlinks_info = item.get("avg_backlinks_info", {}) or {}
            keyword_info = item.get("keyword_info", {}) or {}
            keyword_props = item.get("keyword_properties", {}) or {}
            intent_info = item.get("search_intent_info", {}) or {}
            serp_info = item.get("serp_info", {}) or {}

            serp_item_types = serp_info.get("serp_item_types", []) or []

            # Cast metrics to int as per SERPBacklinks TypedDict
            return {
                "keyword": item.get("keyword", keyword),

                # Core metrics
                "search_volume": int(keyword_info.get("search_volume", 0)) if keyword_info and keyword_info.get("search_volume") else 0,
                "keyword_difficulty": int(keyword_props.get("keyword_difficulty", 0)) if keyword_props and keyword_props.get("keyword_difficulty") else 0,

                # Link metrics
                "backlinks": int(backlinks_info.get("backlinks", 0)) if backlinks_info and backlinks_info.get("backlinks") else 0,
                "referring_domains": int(backlinks_info.get("referring_domains", 0)) if backlinks_info and backlinks_info.get("referring_domains") else 0,
                "dofollow_links": int(backlinks_info.get("dofollow", 0)) if backlinks_info and backlinks_info.get("dofollow") else 0,

                # SERP features (bool)
                "images": True if "images" in serp_item_types else False,
                "videos": True if "videos" in serp_item_types else False,
                "discussions_and_forums": True if "discussions_and_forums" in serp_item_types else False,

                # Intent
                "main_intent": intent_info.get("main_intent", "unknown") if intent_info else "unknown",
                "foreign_intent": ", ".join(intent_info.get("foreign_intent", [])) if intent_info and isinstance(intent_info.get("foreign_intent"), list) else (intent_info.get("foreign_intent", "unknown") if intent_info else "unknown"),
            }
    except Exception as e:
        logger.error(f"Error fetching DataForSEO data: {e}")
        return {}

async def fetch_dataforseo_backlinks(state: REXT) -> Dict[str, Any]:
    serp_payload = state.get("serp_payload")
    default_backlinks = {
        "keyword": "",
        "search_volume": 0,
        "keyword_difficulty": 0,
        "backlinks": 0,
        "referring_domains": 0,
        "dofollow_links": 0,
        "images": False,
        "videos": False,
        "discussions_and_forums": False,
        "main_intent": "unknown",
        "foreign_intent": "unknown",
    }

    # if not serp_payload:
    #     logger.error("No serp_payload found in state")
    #     return {"seo_result": {"serp_backlinks": default_backlinks}}

    query = serp_payload.get("query")
    country = serp_payload.get("country", "Pakistan")
    
    # Handle invalid country codes and global
    if country and country.lower() == "global":
        country = "United States"
    elif country not in VALID_COUNTRY_CODES:
        logger.info(f"Using global fallback (United States) for query: '{query}' due to invalid country: {country}")
        country = "United States"

    if not query:
        logger.error("No query provided in serp_payload")
        return {"seo_result": {"serp_backlinks": default_backlinks}}
    
    default_backlinks["keyword"] = query or ""

    # Check required IDs
    user_id = serp_payload.get("user_id")
    workspace_id = serp_payload.get("workspace_id")
    if not user_id or not workspace_id:
        logger.error("No user_id or workspace_id found in serp_payload")
        return {"seo_result": {"serp_backlinks": default_backlinks}}

    if not DATAFORSEO_BACKLINKS_URL:
        logger.error("DATAFORSEO_BACKLINKS_URL not found in environment variables")
        return {"seo_result": {"serp_backlinks": default_backlinks}}

    try:
        backlinks_data = await get_dataforseo_data(query, country)
        if not backlinks_data:
            logger.warning(f"No DataForSEO data found for query '{query}'")
            return {
                "seo_result":{
                    "serp_backlinks": default_backlinks
                }
            }

        logger.info(f"Successfully fetched SERP backlinks for query '{query}'")
        return {
            "seo_result":{
                "serp_backlinks": backlinks_data
            }
        }

    except Exception as e:
        logger.exception(f"Failed to fetch SERP results for query '{query}': {str(e)}")
        return {
            "seo_result":{
                "serp_backlinks": default_backlinks
            }
        }
