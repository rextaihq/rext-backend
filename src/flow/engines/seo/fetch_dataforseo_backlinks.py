import os
import logging
from typing import Dict, Any
from dotenv import load_dotenv
import httpx

from src.flow.states.rext import REXT
from src.flow.states.countries import VALID_COUNTRY_CODES

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
# 🛠️ SAFE UTILS
# =========================
def safe_int(value: Any, default: int = 0) -> int:
    """Safely convert value to int, fallback to default."""
    try:
        if value is None:
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


# =========================
# 🚀 MAIN FUNCTION (SINGLE KEYWORD)
# =========================
async def get_dataforseo_data(
    keyword: str,
    location_name: str = "United States",
    language_code: str = "en",
    include_serp_info: bool = True
) -> Dict[str, Any]:

    payload = [{
        "location_name": location_name,
        "language_code": language_code,
        "keywords": [keyword],
        "include_serp_info": include_serp_info
    }]

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                DATAFORSEO_BACKLINKS_URL,
                headers=headers,
                json=payload
            )
            response.raise_for_status()
            data = response.json()

        # 🔍 Validate response structure
        tasks = data.get("tasks") or []
        if not tasks:
            logger.warning("No tasks in DataForSEO response")
            return {}

        result = tasks[0].get("result") or []
        if not result:
            logger.warning("No result in DataForSEO response")
            return {}

        items = result[0].get("items") or []
        if not items:
            logger.warning("No items in DataForSEO response")
            return {}

        item = items[0]

        # 🧪 Debug log (very useful)
        logger.debug(f"DataForSEO raw item: {item}")

        backlinks_info = item.get("avg_backlinks_info") or {}
        keyword_info = item.get("keyword_info") or {}
        keyword_props = item.get("keyword_properties") or {}
        intent_info = item.get("search_intent_info") or {}
        serp_info = item.get("serp_info") or {}

        serp_item_types = serp_info.get("serp_item_types") or []

        return {
            "keyword": item.get("keyword", keyword),

            # 📊 Core metrics
            "search_volume": safe_int(keyword_info.get("search_volume")),
            "keyword_difficulty": safe_int(keyword_props.get("keyword_difficulty")),

            # 🔗 Link metrics (may be missing in this endpoint)
            "backlinks": safe_int(backlinks_info.get("backlinks")),
            "referring_domains": safe_int(backlinks_info.get("referring_domains")),
            "dofollow_links": safe_int(backlinks_info.get("dofollow")),

            # 🧩 SERP features
            "images": "images" in serp_item_types,
            "videos": "videos" in serp_item_types,
            "discussions_and_forums": "discussions_and_forums" in serp_item_types,

            # 🎯 Intent
            "main_intent": intent_info.get("main_intent") or "unknown",
            "foreign_intent": ", ".join(intent_info.get("foreign_intent", []))
            if isinstance(intent_info.get("foreign_intent"), list)
            else (intent_info.get("foreign_intent") or "unknown"),
        }

    except httpx.HTTPError as e:
        logger.error(f"HTTP error from DataForSEO: {e}")
        return {}
    except Exception as e:
        logger.exception(f"Unexpected error fetching DataForSEO data: {e}")
        return {}


# =========================
# 🔄 LANGGRAPH NODE
# =========================
async def fetch_dataforseo_backlinks(state: REXT) -> Dict[str, Any]:

    serp_payload = state.get("serp_payload") or {}

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

    query = serp_payload.get("query")
    country = serp_payload.get("country", "United States")

    if not query:
        logger.error("No query provided in serp_payload")
        return {"seo_result": {"serp_backlinks": default_backlinks}}

    # 🌍 Normalize country
    if country.lower() == "global":
        country = "United States"
    elif country not in VALID_COUNTRY_CODES:
        logger.info(
            f"Invalid country '{country}', falling back to United States for query '{query}'"
        )
        country = "United States"

    default_backlinks["keyword"] = query

    # 🔐 Validate required IDs
    user_id = serp_payload.get("user_id")
    workspace_id = serp_payload.get("workspace_id")

    if not user_id or not workspace_id:
        logger.error("Missing user_id or workspace_id in serp_payload")
        return {"seo_result": {"serp_backlinks": default_backlinks}}

    try:
        backlinks_data = await get_dataforseo_data(query, country)

        if not backlinks_data:
            logger.warning(f"No DataForSEO data found for query '{query}'")
            return {"seo_result": {"serp_backlinks": default_backlinks}}

        logger.info(f"Successfully fetched SEO data for query '{query}'")

        return {
            "seo_result": {
                "serp_backlinks": backlinks_data
            }
        }

    except Exception as e:
        logger.exception(f"Failed to fetch DataForSEO data for query '{query}': {e}")
        return {"seo_result": {"serp_backlinks": default_backlinks}}