import httpx
import logging
import os
from typing import Dict, Any, List
from src.flow.states.rext import REXT, SERPEngineState
from src.flow.states.countries import VALID_COUNTRY_CODES

logger = logging.getLogger(__name__)

from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=10),
    retry=retry_if_exception_type((httpx.RequestError, httpx.TimeoutException)),
    reraise=True
)
async def _do_fetch_serp(client: httpx.AsyncClient, query: str, country: str, api_key: str) -> Dict[str, Any]:
    if country == "global":
        country = ""
    payload = {"q": query, "gl": country}
    headers = {
        "X-API-KEY": api_key,
        "Content-Type": "application/json"
    }

    logger.debug(f"Sending request to Serper.dev for query: {query}")
    response = await client.post(
        "https://google.serper.dev/search",
        json=payload,
        headers=headers,
        timeout=30.0
    )

    if response.status_code != 200:
        logger.error(f"Failed to fetch SERP results. Status: {response.status_code}, Reason: {response.text}")
        response.raise_for_status()

    return response.json()

def _parse_serp_response(raw_data: Dict[str, Any]) -> SERPEngineState:
    """Parses raw Serper.dev response into SERPEngineState."""
    search_params = raw_data.get("searchParameters", {})
    search_information = raw_data.get("searchInformation", {})

    # Organic Results
    organic_results = [
        {
            "position": item.get("position"),
            "title": item.get("title", "").strip(),
            "snippet": item.get("snippet", "").strip(),
            "link": item.get("link"),
            "date": item.get("date"),
            "sitelinks": item.get("sitelinks", [])
        }
        for item in raw_data.get("organic", [])
    ]

    # People Also Ask
    people_ask = [
        {
            "question": item.get("question"),
            "snippet": item.get("snippet"),
            "title": item.get("title"),
            "link": item.get("link")
        }
        for item in raw_data.get("peopleAlsoAsk", [])
    ]

    # Related Searches
    related_searches = [
        r.get("query") for r in raw_data.get("relatedSearches", [])
    ]

    return {
        "search_params": search_params,
        "search_information": search_information,
        "organic_results": organic_results,
        "related_searches": related_searches,
        "people_ask": people_ask,
        "total_results": len(organic_results)
    }

async def fetch_serp_results(state: REXT) -> Dict[str, Any]:
    """
    Fetch raw Google SERP results for a given keyword using the Serper.dev API.
    """
    serp_payload = state.get("serp_payload")
    if not serp_payload:
        logger.error("No serp_payload found in state")
        return {"serp_result": {}}

    query = serp_payload.get("query")
    country = serp_payload.get("country", "us")
    
    if country not in VALID_COUNTRY_CODES:
        logger.warning(f"Invalid country code '{country}' provided. Defaulting to 'us'.")
        country = "us"

    if not query:
        logger.error("No query provided in serp_payload")
        return {"serp_result": {}}

    logger.info(f"Fetching SERP results for query: '{query}' in country: '{country}'")

    # get the user_id and workspace_id from the state
    user_id = serp_payload.get("user_id")
    workspace_id = serp_payload.get("workspace_id")
    
    if not user_id or not workspace_id:
        logger.error("No user_id or workspace_id found in serp_payload")
        return {"serp_result": {}}

    api_key = os.getenv("SERPER_API_KEY")
    if not api_key:
        logger.error("SERPER_API_KEY not found in environment variables")
        return {"serp_result": {}}

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            raw_data = await _do_fetch_serp(client, query, country, api_key)
            serp_data = _parse_serp_response(raw_data)
            
            logger.info(f"Successfully fetched and parsed {serp_data['total_results']} organic results")
            return {"serp_result": serp_data}

    except Exception as e:
        logger.exception(f"Failed to fetch SERP results for query '{query}': {str(e)}")
        return {"serp_result": {}}