import os
import logging
from typing import Any, Dict

import httpx
from dotenv import load_dotenv

from src.flow.states.countries import VALID_COUNTRY_CODES
from src.flow.states.rext import REXT

load_dotenv()

logger = logging.getLogger(__name__)

DATAFORSEO_BACKLINKS_URL = os.getenv("DATAFORSEO_BACKLINKS_URL")
AUTH_HEADER = os.getenv("DATAFORSEO_AUTH_HEADER")

if not DATAFORSEO_BACKLINKS_URL or not AUTH_HEADER:
    raise EnvironmentError("Missing DataForSEO environment variables")

headers = {
    "Authorization": f"Basic {AUTH_HEADER}",
    "Content-Type": "application/json",
}


async def get_dataforseo_data(
    keyword: str,
    location_name: str = "United States",
    language_code: str = "en",
    include_serp_info: bool = True,
) -> Dict[str, Any]:
    payload_item = {
        "location_name": location_name,
        "language_code": language_code,
        "include_serp_info": include_serp_info,
    }

    if "keyword_overview" in DATAFORSEO_BACKLINKS_URL:
        payload_item["keywords"] = [keyword]
    else:
        payload_item["keyword"] = keyword
        payload_item["include_seed_keyword"] = True

    payload = [payload_item]

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                DATAFORSEO_BACKLINKS_URL,
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

            tasks = data.get("tasks", [])
            if not tasks:
                return {}

            result = tasks[0].get("result")
            if not result or not result[0]:
                return {}

            item = result[0].get("seed_keyword_data", {})
            if not item:
                items = result[0].get("items", [])
                if items:
                    item = items[0]
                else:
                    return {}

            backlinks_info = item.get("avg_backlinks_info", {}) or {}
            keyword_info = item.get("keyword_info", {}) or {}
            keyword_props = item.get("keyword_properties", {}) or {}
            serp_info = item.get("serp_info", {}) or {}

            serp_item_types = serp_info.get("serp_item_types", []) or []

            # Intent is intentionally disconnected from DataForSEO.
            return {
                "keyword": item.get("keyword", keyword),
                "search_volume": int(keyword_info.get("search_volume", 0))
                if keyword_info and keyword_info.get("search_volume")
                else 0,
                "keyword_difficulty": int(keyword_props.get("keyword_difficulty", 0))
                if keyword_props and (keyword_props.get("keyword_difficulty") is not None)
                else 0,
                "backlinks": int(backlinks_info.get("backlinks", 0))
                if backlinks_info and backlinks_info.get("backlinks")
                else 0,
                "referring_domains": int(backlinks_info.get("referring_domains", 0))
                if backlinks_info and backlinks_info.get("referring_domains")
                else 0,
                "dofollow_links": int(backlinks_info.get("dofollow", 0))
                if backlinks_info and backlinks_info.get("dofollow")
                else 0,
                "images": "images" in serp_item_types,
                "videos": "videos" in serp_item_types,
                "discussions_and_forums": "discussions_and_forums" in serp_item_types,
                "main_intent": "informational",
                "foreign_intent": "informational",
            }
    except Exception as e:
        logger.error("Error fetching DataForSEO data: %s", e)
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
        "main_intent": "informational",
        "foreign_intent": "informational",
    }

    query = serp_payload.get("query")
    country = serp_payload.get("country", "Pakistan")

    if country and country.lower() == "global":
        country = "United States"
    elif country not in VALID_COUNTRY_CODES:
        logger.info(
            "Using global fallback (United States) for query: '%s' due to invalid country: %s",
            query,
            country,
        )
        country = "United States"

    if not query:
        logger.error("No query provided in serp_payload")
        return {"seo_result": {"serp_backlinks": default_backlinks}}

    default_backlinks["keyword"] = query or ""

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
            logger.warning("No DataForSEO data found for query '%s'", query)
            return {"seo_result": {"serp_backlinks": default_backlinks}}

        logger.info("Successfully fetched SERP backlinks for query '%s'", query)
        return {"seo_result": {"serp_backlinks": backlinks_data}}

    except Exception as e:
        logger.exception("Failed to fetch SERP results for query '%s': %s", query, str(e))
        return {"seo_result": {"serp_backlinks": default_backlinks}}
