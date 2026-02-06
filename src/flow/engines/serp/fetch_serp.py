import httpx
import logging
from typing import Dict, Any, List
from src.flow.states.rext import REXT, SERPEngineState
from src.flow.states.countries import VALID_COUNTRY_CODES
from dotenv import load_dotenv
import os

load_dotenv()

logger = logging.getLogger(__name__)

from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
AUTH_HEADER = os.getenv("DATAFORSEO_AUTH_HEADER")
DATAFORSEO_SERP_URL = os.getenv("DATAFORSEO_SERP_URL")

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=10),
    retry=retry_if_exception_type((httpx.RequestError, httpx.TimeoutException)),
    reraise=True
)
async def _do_fetch_serp(
    client: httpx.AsyncClient,
    query: str,
    country: str,
    serp_url: str = DATAFORSEO_SERP_URL,
    auth_header: str = AUTH_HEADER
) -> Dict[str, Any]:

    if country == "Global":
        country = "United States"

    payload = [
        {
            "keyword": query,
            "location_name": country,
            "language_code": "en"
        }
    ]

    headers = {
        "Authorization": f"Basic {auth_header}",
        "Content-Type": "application/json"
    }

    logger.debug(f"Sending request to DataForSEO (live) for query: {query}")

    response = await client.post(
        serp_url,
        json=payload,
        headers=headers,
        # timeout=30.0
    )

    if response.status_code != 200:
        logger.error(
            f"DataForSEO request failed. "
            f"Status: {response.status_code}, Response: {response.text}"
        )
        response.raise_for_status()
    return response.json()


def _parse_serp_response(raw_data: Dict[str, Any]) -> SERPEngineState:
    task = raw_data.get("tasks", [{}])[0]
    result = task.get("result", [{}])[0]
    items = result.get("items", [])

    serp_state: SERPEngineState = {
        "search_params": task.get("data", {}),

        "organic_results": [],
        "people_ask": [],
        "related_searches": [],

        "total_results": 0
    }

    for item in items:
        item_type = item.get("type")

        # ----------------------------
        # ORGANIC
        # ----------------------------
        if item_type == "organic":
            serp_state["organic_results"].append({
                "position": item.get("rank_group", ""),
                "absolute_position": item.get("rank_absolute", ""),
                "title": item.get("title", ""),
                "snippet": item.get("description", ""),
                "link": item.get("url", ""),
                "domain": item.get("domain", ""),
                "breadcrumb": item.get("breadcrumb", ""),
                "is_image": item.get("is_image", False),
                "is_video": item.get("is_video", False),
                "faqs": item.get("faqs", False),
                "is_featured_snippet": item.get("is_featured_snippet", False),
            })

        # ----------------------------
        # RELATED SEARCHES
        # ----------------------------
        elif item_type in ("related_searches", "related_search"):
            for r in item.get("items", []):
                value = r if isinstance(r, str) else r.get("query", "")
                if value:
                    serp_state["related_searches"].append(value)

        # ----------------------------
        # PEOPLE ALSO ASK
        # ----------------------------
        elif item_type == "people_also_ask":
            data = item.get("items", [])
            for d in data:
                expanded_element = d.get("expanded_element", {})
                serp_state["people_ask"].append({
                    "question": d.get("title", ""),
                    "snippet": expanded_element.get("description", ""),
                    "link": expanded_element.get("url", ""),
                    "domain": expanded_element.get("domain", ""),
                    "title": expanded_element.get("title", ""),
                })

    serp_state["total_results"] = len(serp_state["organic_results"])
    return serp_state

async def fetch_serp_results(state: REXT) -> Dict[str, Any]:
    """
    Fetch Google SERP results for a given keyword using DataForSEO API.
    Handles global queries, logs all SERP type counts, and returns enriched SERPEngineState.
    """
    serp_payload = state.get("serp_payload")
    if not serp_payload:
        logger.error("No serp_payload found in state")
        return {"serp_result": {}}

    query = serp_payload.get("query")
    country = serp_payload.get("country", "Pakistan")
    
    # Handle invalid country codes and global
    if country == "global" or country not in VALID_COUNTRY_CODES:
        logger.info(f"Using global SERP (no location) for query: '{query}'")
        country = None

    if not query:
        logger.error("No query provided in serp_payload")
        return {"serp_result": {}}

    # Check required IDs
    user_id = serp_payload.get("user_id")
    workspace_id = serp_payload.get("workspace_id")
    if not user_id or not workspace_id:
        logger.error("No user_id or workspace_id found in serp_payload")
        return {"serp_result": {}}

    if not DATAFORSEO_SERP_URL:
        logger.error("DATAFORSEO_SERP_URL not found in environment variables")
        return {"serp_result": {}}

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            raw_data = await _do_fetch_serp(client, query, country, DATAFORSEO_SERP_URL)
            serp_data = _parse_serp_response(raw_data)

            # Log counts for each SERP type
            logger.info(f"Fetched SERP for query '{query}': {serp_data}")

            return {"serp_result": serp_data}

    except Exception as e:
        logger.exception(f"Failed to fetch SERP results for query '{query}': {str(e)}")
        return {"serp_result": {}}
