import asyncio
import logging
import os
from typing import Any, Dict

import httpx
from dotenv import load_dotenv

from src.flow.states.countries import ISO_TO_COUNTRY, VALID_COUNTRY_CODES
from src.flow.states.rext import REXT, SERPEngineState

load_dotenv()

logger = logging.getLogger(__name__)

AUTH_HEADER = os.getenv("DATAFORSEO_AUTH_HEADER")
DATAFORSEO_SERP_URL = os.getenv("DATAFORSEO_SERP_URL")

# DataForSEO's live SERP answers in 15 to 30 seconds and allows itself 120
# (50401); on 2026-10-05 three live calls took 17 s, 25 s and over 30 s. A call
# abandoned at the client is still billed when it completes, so the wait is
# long enough for the slow tail rather than retried early.
SERP_TIMEOUT_SECONDS = 60.0


# @retry(
#     stop=stop_after_attempt(3),
#     wait=wait_exponential(multiplier=1, min=4, max=10),
#     retry=retry_if_exception_type((httpx.RequestError, httpx.TimeoutException)),
#     reraise=True
# )
async def _do_fetch_serp(
    client: httpx.AsyncClient,
    query: str,
    country: str,
    serp_url: str = DATAFORSEO_SERP_URL,
    auth_header: str = AUTH_HEADER,
) -> Dict[str, Any]:

    # Default to United States for Global or missing country
    if not country or country.lower() == "global":
        country = "United States"

    payload = [{"keyword": query, "location_name": country, "language_code": "en"}]

    headers = {"Authorization": f"Basic {auth_header}", "Content-Type": "application/json"}

    logger.debug(
        f"Sending request to DataForSEO (live) for query: {query} with location: {country}"
    )

    response = await client.post(
        serp_url, json=payload, headers=headers, timeout=SERP_TIMEOUT_SECONDS
    )

    if response.status_code != 200:
        logger.error(
            f"DataForSEO request failed. Status: {response.status_code}, Response: {response.text}"
        )
        response.raise_for_status()
    return response.json()


def _empty_serp_state() -> SERPEngineState:
    """A fully-keyed empty SERP result.

    ``serp_result`` is merged into the previous value, so returning ``{}`` on a
    failed fetch would silently keep the previous keyword/country's SERP. Every
    key is spelled out so a failed re-analysis overwrites it with nothing.
    """
    return {
        "search_params": {},
        "organic_results": [],
        "people_ask": [],
        "related_searches": [],
        "total_results": 0,
        "serp_status": "lookup_failed",
        "ai_overview": None,
    }


# DataForSEO task codes that mean the search ran and found nothing, as opposed
# to the search failing (https://docs.dataforseo.com/v3/appendix/errors/).
_NO_RESULTS_STATUS_CODES = {20000, 40102}


# A failure that is gone a moment later: the search engine's own error (40101),
# DataForSEO's system errors (50000-50999: a live-mode timeout and the like), a
# network timeout or an HTTP 5xx. One retry absorbs it; on 2026-10-05 a 40101
# for a keyword whose SERP came back normally a minute later ended a run.
SERP_ATTEMPTS = 2
SERP_RETRY_DELAY_SECONDS = 2.0


def _task_status(raw_data: Dict[str, Any]) -> Any:
    """The first task's status, else the response's own (a reply with no task
    carries its error, e.g. a 50000, only at the top level)."""
    tasks = raw_data.get("tasks") or [{}]
    status = (tasks[0] or {}).get("status_code")
    return status if status is not None else raw_data.get("status_code")


def _is_passing_status(status_code: Any) -> bool:
    return status_code == 40101 or (isinstance(status_code, int) and 50000 <= status_code < 51000)


def _is_passing_error(error: Exception) -> bool:
    if isinstance(error, httpx.HTTPStatusError):
        return error.response.status_code >= 500
    return isinstance(error, (httpx.TimeoutException, httpx.TransportError))


def _serp_status(status_code: Any, organic_results: list) -> str:
    if organic_results:
        return "ok"
    return "no_results" if status_code in _NO_RESULTS_STATUS_CODES else "lookup_failed"


def _parse_serp_response(raw_data: Dict[str, Any]) -> SERPEngineState:
    tasks = raw_data.get("tasks", [])
    if not tasks:
        logger.warning("DataForSEO returned no tasks")
        return _empty_serp_state()

    task = tasks[0]
    status_code = task.get("status_code")
    if status_code != 20000:
        logger.error(
            f"DataForSEO task failed with status {status_code}: {task.get('status_message')}"
        )
        # We still try to extract what we can, but likely it's empty

    result = task.get("result", [{}])
    if not result or not result[0]:
        return {
            "search_params": task.get("data", {}),
            "organic_results": [],
            "people_ask": [],
            "related_searches": [],
            "total_results": 0,
            "serp_status": _serp_status(status_code, []),
            "ai_overview": None,
        }

    main_result = result[0]
    # A search with no results comes back with "items": null.
    items = main_result.get("items") or []

    serp_state: SERPEngineState = {
        "search_params": task.get("data", {}),
        "organic_results": [],
        "people_ask": [],
        "related_searches": [],
        "total_results": 0,
        # True when DataForSEO returned an "ai_overview" item, None otherwise:
        # without load_async_ai_overview (an extra $0.002 a call) it returns
        # only cached AI Overviews, so a missing item does not prove absence.
        "ai_overview": None,
    }

    item_types = [item.get("type") for item in items]
    logger.debug(f"DataForSEO returned {len(items)} items. Types: {item_types}")

    for item in items:
        item_type = item.get("type")

        # ----------------------------
        # ORGANIC & FEATURED SNIPPET
        # ----------------------------
        if item_type in ("organic", "featured_snippet"):
            serp_state["organic_results"].append(
                {
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
                    "is_featured_snippet": item.get("is_featured_snippet", True)
                    if item_type == "featured_snippet"
                    else item.get("is_featured_snippet", False),
                }
            )

        # ----------------------------
        # RELATED SEARCHES
        # ----------------------------
        elif item_type in ("related_searches", "related_search"):
            for r in item.get("items") or []:
                value = r if isinstance(r, str) else r.get("query", "")
                if value:
                    serp_state["related_searches"].append(value)

        elif item_type == "ai_overview":
            serp_state["ai_overview"] = True

        # ----------------------------
        # PEOPLE ALSO ASK
        # ----------------------------
        elif item_type == "people_also_ask":
            data = item.get("items") or []
            for d in data:
                expanded_element = d.get("expanded_element") or []
                for exp_elm in expanded_element:
                    serp_state["people_ask"].append(
                        {
                            "question": d.get("title", ""),
                            "snippet": exp_elm.get("description", ""),
                            "link": exp_elm.get("url", ""),
                            "domain": exp_elm.get("domain", ""),
                            "title": exp_elm.get("title", ""),
                        }
                    )

    serp_state["total_results"] = len(serp_state["organic_results"])
    serp_state["serp_status"] = _serp_status(status_code, serp_state["organic_results"])
    return serp_state


async def fetch_serp_results(state: REXT, config, *, runtime):
    """
    Fetch Google SERP results for a given keyword using DataForSEO API.
    Handles global queries, logs all SERP type counts, and returns enriched SERPEngineState.
    """
    # Access the store from runtime
    _store = runtime.store

    serp_payload = state.get("serp_payload")
    if not serp_payload:
        logger.error("No serp_payload found in state")
        return {"serp_result": _empty_serp_state()}

    query = serp_payload.get("query")
    country = serp_payload.get("country", "Pakistan")

    if country:
        if country.lower() == "global":
            country = "United States"
        else:
            country = ISO_TO_COUNTRY.get(country.lower(), country)
            if country not in VALID_COUNTRY_CODES:
                logger.warning(
                    f"Country '{country}' not in valid list, defaulting to None (Global strategy)"
                )
                country = None

    if not query:
        logger.error("No query provided in serp_payload")
        return {"serp_result": _empty_serp_state()}

    # Check required IDs
    user_id = serp_payload.get("user_id")
    workspace_id = serp_payload.get("workspace_id")
    if not user_id or not workspace_id:
        logger.error("No user_id or workspace_id found in serp_payload")
        return {"serp_result": _empty_serp_state()}

    if not DATAFORSEO_SERP_URL:
        logger.error("DATAFORSEO_SERP_URL not found in environment variables")
        return {"serp_result": _empty_serp_state()}

    for attempt in range(1, SERP_ATTEMPTS + 1):
        last_attempt = attempt == SERP_ATTEMPTS
        try:
            async with httpx.AsyncClient(timeout=SERP_TIMEOUT_SECONDS) as client:
                raw_data = await _do_fetch_serp(client, query, country, DATAFORSEO_SERP_URL)
                serp_data = _parse_serp_response(raw_data)
        except Exception as e:
            if not last_attempt and _is_passing_error(e):
                logger.warning(f"SERP lookup for '{query}' failed ({e}); retrying")
                await asyncio.sleep(SERP_RETRY_DELAY_SECONDS)
                continue
            logger.exception(f"Failed to fetch SERP results for query '{query}': {str(e)}")
            return {"serp_result": _empty_serp_state()}

        status_code = _task_status(raw_data)
        if (
            not last_attempt
            and serp_data["serp_status"] == "lookup_failed"
            and _is_passing_status(status_code)
        ):
            logger.warning(f"SERP lookup for '{query}' got task status {status_code}; retrying")
            await asyncio.sleep(SERP_RETRY_DELAY_SECONDS)
            continue

        # Log summary for debugging
        logger.info(
            f"Fetched SERP for query '{query}': Found {len(serp_data['organic_results'])} organic results, {len(serp_data['related_searches'])} related searches, {len(serp_data['people_ask'])} questions."
        )
        return {"serp_result": serp_data}
