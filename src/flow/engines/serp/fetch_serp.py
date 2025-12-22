import json
import http.client
import logging
from typing import Dict, Any, List
from src.flow.states.wrext import WREXT, SERPEngineState
from dotenv import load_dotenv
import os

load_dotenv()

logger = logging.getLogger(__name__)

def fetch_serp_results(state: WREXT) -> Dict[str, Any]:
    """
    Fetch raw Google SERP results for a given keyword using the Serper.dev API.

    Args:
        state (WREXT): The current state containing the search query.

    Returns:
        Dict[str, Any]: A dictionary containing the updated SERP engine state.
    """
    serp_payload = state.get("serp_payload")
    if not serp_payload:
        logger.error("No serp_payload found in state")
        return {"serp_result": {}}

    query = serp_payload.get("query")
    country = serp_payload.get("country", "us")
    
    logger.info(f"Fetching SERP results for query: '{query}' in country: '{country}'")

    api_key = os.getenv("SERPER_API_KEY")
    if not api_key:
        logger.error("SERPER_API_KEY not found in environment variables")
        return {"serp_result": {}}

    try:
        conn = http.client.HTTPSConnection("google.serper.dev")
        payload = json.dumps({"q": query, "gl": country})
        headers = {
            "X-API-KEY": api_key,
            "Content-Type": "application/json"
        }

        logger.debug(f"Sending request to Serper.dev for query: {query}")
        conn.request("POST", "/search", payload, headers)

        res = conn.getresponse()
        
        if res.status != 200:
            logger.error(f"Failed to fetch SERP results. Status: {res.status}, Reason: {res.reason}")
            return {"serp_result": {}}

        raw_data = json.loads(res.read().decode("utf-8"))
        logger.debug("Successfully received response from Serper.dev")

    except Exception as e:
        logger.exception(f"An error occurred while fetching SERP results: {str(e)}")
        return {"serp_result": {}}
    finally:
        if conn:
            conn.close()


    # -------- Search Parameters --------
    search_params = raw_data.get("searchParameters", {})

    # -------- Search Information (spelling, corrections, etc.) --------
    search_information = raw_data.get("searchInformation", {})

    # -------- Organic Results --------
    organic_results: List[Dict[str, Any]] = []
    for item in raw_data.get("organic", []):
        organic_results.append({
            "position": item.get("position"),
            "title": item.get("title", "").strip(),
            "snippet": item.get("snippet", "").strip(),
            "link": item.get("link"),
            "date": item.get("date"),
            "sitelinks": item.get("sitelinks", [])
        })
    logger.debug(f"Extracted {len(organic_results)} organic results")

    # -------- People Also Ask --------
    people_ask: List[Dict[str, Any]] = []
    for item in raw_data.get("peopleAlsoAsk", []):
        people_ask.append({
            "question": item.get("question"),
            "snippet": item.get("snippet"),
            "title": item.get("title"),
            "link": item.get("link")
        })
    logger.debug(f"Extracted {len(people_ask)} 'People Also Ask' items")

    # -------- Related Searches --------
    related_searches: List[str] = [
        r.get("query") for r in raw_data.get("relatedSearches", [])
    ]
    logger.debug(f"Extracted {len(related_searches)} related searches")

    # -------- Build SERP Engine State --------
    serp_data: SERPEngineState = {
        "search_params": search_params,
        "search_information": search_information,
        "organic_results": organic_results,
        "related_searches": related_searches,
        "people_ask": people_ask,
        "total_results": len(organic_results)
    }

    logger.info(f"Completed SERP fetching for query: '{query}'")
    return {
        "serp_result": serp_data
    }