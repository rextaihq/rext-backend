import requests
import json
import os
import logging
from dotenv import load_dotenv
from typing import Dict, Any, List
from src.flow.states.rext import REXT
import httpx
from src.flow.states.countries import VALID_COUNTRY_CODES
from src.flow.states.rext import SERPBacklinks

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
def get_dataforseo_data(
    keyword: str,
    location_name: str = "United States",
    language_code: str = "en",
    include_serp_info: bool = True
) -> Dict:

    payload = [{
        "location_name": location_name,
        "language_code": language_code,
        "keywords": [keyword],   # ✅ single keyword wrapped in list
        "include_serp_info": include_serp_info
    }]

    response = requests.post(DATAFORSEO_BACKLINKS_URL, headers=headers, json=payload)
    response.raise_for_status()

    data = response.json()

    items = data.get("tasks", [])[0].get("result", [])[0].get("items", [])

    if not items:
        return {}

    item = items[0]  # ✅ single keyword → first item

    backlinks_info = item.get("avg_backlinks_info", {})
    keyword_info = item.get("keyword_info", {})
    keyword_props = item.get("keyword_properties", {})
    intent_info = item.get("search_intent_info", {})
    serp_info = item.get("serp_info", {})

    serp_item_types = serp_info.get("serp_item_types", [])

    return {
        "keyword": item.get("keyword"),

        # Core metrics
        "search_volume": keyword_info.get("search_volume"),
        "keyword_difficulty": keyword_props.get("keyword_difficulty"),

        # Link metrics
        "backlinks": backlinks_info.get("backlinks", 0),
        "referring_domains": backlinks_info.get("referring_domains", 0),
        "dofollow_links": backlinks_info.get("dofollow", 0),

        # SERP features (bool)
        "images": "images" in serp_item_types,
        "videos": "videos" in serp_item_types,

        # Intent
        "main_intent": intent_info.get("main_intent"),
        "foreign_intent": intent_info.get("foreign_intent"),
    }

async def fetch_dataforseo_backlinks(state: REXT) -> SERPBacklinks:
    serp_payload = state.get("serp_payload")
    if not serp_payload:
        logger.error("No serp_payload found in state")
        return {"serp_backlinks": {}}

    query = serp_payload.get("query")
    country = serp_payload.get("country", "Pakistan")
    
    # Handle invalid country codes and global
    if country == "global" or country not in VALID_COUNTRY_CODES:
        logger.info(f"Using global SERP (no location) for query: '{query}'")
        country = None

    if not query:
        logger.error("No query provided in serp_payload")
        return {"serp_backlinks": {}}

    # Check required IDs
    user_id = serp_payload.get("user_id")
    workspace_id = serp_payload.get("workspace_id")
    if not user_id or not workspace_id:
        logger.error("No user_id or workspace_id found in serp_payload")
        return {"serp_backlinks": {}}

    if not DATAFORSEO_BACKLINKS_URL:
        logger.error("DATAFORSEO_BACKLINKS_URL not found in environment variables")
        return {"serp_backlinks": {}}

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            backlinks_data = await get_dataforseo_data(query, country)

            # Log counts for each SERP type
            logger.info(f"Fetched SERP for query '{query}': {backlinks_data}")

            return {"serp_backlinks": backlinks_data}

    except Exception as e:
        logger.exception(f"Failed to fetch SERP results for query '{query}': {str(e)}")
        return {"serp_backlinks": {}}
