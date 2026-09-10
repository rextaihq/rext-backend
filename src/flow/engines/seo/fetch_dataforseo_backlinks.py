import logging
import os
from typing import Any, Dict

import httpx
from dotenv import load_dotenv

from src.flow.states.rext import REXT
from src.flow.states.seo_state import SERPBacklinks

load_dotenv()

logger = logging.getLogger(__name__)

DATAFORSEO_BACKLINKS_URL = os.getenv("DATAFORSEO_BACKLINKS_URL")
AUTH_HEADER = os.getenv("DATAFORSEO_AUTH_HEADER")

if not DATAFORSEO_BACKLINKS_URL or not AUTH_HEADER:
    raise EnvironmentError(
        "Missing DATAFORSEO_BACKLINKS_URL or DATAFORSEO_AUTH_HEADER in environment"
    )

HEADERS = {
    "Authorization": f"Basic {AUTH_HEADER}",
    "Content-Type": "application/json",
}

ISO_TO_COUNTRY: Dict[str, str] = {
    "us": "United States",
    "gb": "United Kingdom",
    "ca": "Canada",
    "au": "Australia",
    "de": "Germany",
    "fr": "France",
    "in": "India",
    "pk": "Pakistan",
    "ae": "United Arab Emirates",
    "sg": "Singapore",
    "nz": "New Zealand",
    "za": "South Africa",
    "ng": "Nigeria",
    "gh": "Ghana",
    "ke": "Kenya",
    "ie": "Ireland",
    "nl": "Netherlands",
    "se": "Sweden",
    "no": "Norway",
    "dk": "Denmark",
    "fi": "Finland",
    "it": "Italy",
    "es": "Spain",
    "pt": "Portugal",
    "br": "Brazil",
    "mx": "Mexico",
    "ar": "Argentina",
    "co": "Colombia",
    "jp": "Japan",
    "kr": "South Korea",
    "cn": "China",
    "ph": "Philippines",
    "id": "Indonesia",
    "my": "Malaysia",
    "th": "Thailand",
    "bd": "Bangladesh",
    "lk": "Sri Lanka",
}

COUNTRY_LANGUAGE_MAP: Dict[str, str] = {
    "United States": "en",
    "United Kingdom": "en",
    "Canada": "en",
    "Australia": "en",
    "New Zealand": "en",
    "Ireland": "en",
    "South Africa": "en",
    "Nigeria": "en",
    "Ghana": "en",
    "Kenya": "en",
    "Germany": "de",
    "France": "fr",
    "Spain": "es",
    "Mexico": "es",
    "Argentina": "es",
    "Colombia": "es",
    "Portugal": "pt",
    "Brazil": "pt",
    "Italy": "it",
    "Netherlands": "nl",
    "Sweden": "sv",
    "Norway": "no",
    "Denmark": "da",
    "Finland": "fi",
    "Japan": "ja",
    "South Korea": "ko",
    "China": "zh",
    "India": "en",
    "Pakistan": "en",
    "Bangladesh": "en",
    "Singapore": "en",
    "Philippines": "en",
    "Malaysia": "en",
    "Thailand": "th",
    "Indonesia": "id",
    "Sri Lanka": "en",
    "United Arab Emirates": "en",
}


def resolve_country(raw: str) -> tuple[str, str]:
    """Returns (location_name, language_code) from ISO code or full country name."""
    if not raw or raw.lower() == "global":
        return "United States", "en"
    full_name = ISO_TO_COUNTRY.get(raw.lower())
    if full_name:
        return full_name, COUNTRY_LANGUAGE_MAP.get(full_name, "en")
    return raw, COUNTRY_LANGUAGE_MAP.get(raw, "en")


async def get_dataforseo_data(
    keyword: str,
    location_name: str = "United States",
    language_code: str = "en",
) -> Dict[str, Any]:
    """
    Calls DATAFORSEO_BACKLINKS_URL (keyword_overview/live).
    Returns search_volume, keyword_difficulty, intent, avg backlinks, referring_domains.
    """
    payload = [
        {
            "keywords": [keyword],
            "location_name": location_name,
            "language_code": language_code,
        }
    ]

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(DATAFORSEO_BACKLINKS_URL, headers=HEADERS, json=payload)
            response.raise_for_status()
            data = response.json()

        task = data.get("tasks", [{}])[0]
        if task.get("status_code") != 20000:
            logger.warning(f"DataForSEO error: {task.get('status_message')}")
            return {}

        result = task.get("result") or []
        if not result:
            logger.warning(f"Empty result from DataForSEO for: {keyword}")
            return {}

        # keyword_overview: result[0]["items"] is the list of keyword objects
        items = result[0].get("items") or []
        if not items:
            logger.warning(f"No items in result for: {keyword}")
            return {}

        item = items[0]

        ki = item.get("keyword_info", {}) or {}
        kp = item.get("keyword_properties", {}) or {}
        intent = item.get("search_intent_info", {}) or {}
        bl = item.get("avg_backlinks_info", {}) or {}
        serp = item.get("serp_info", {}) or {}

        serp_types = serp.get("serp_item_types", []) or []

        foreign_intent = intent.get("foreign_intent", [])
        if isinstance(foreign_intent, list):
            foreign_intent = ", ".join(foreign_intent)

        return {
            "keyword": item.get("keyword", keyword),
            "search_volume": int(ki.get("search_volume") or 0),
            "keyword_difficulty": int(kp.get("keyword_difficulty") or 0),
            "backlinks": int(bl.get("backlinks") or 0),
            "referring_domains": int(bl.get("referring_domains") or 0),
            "dofollow_links": int(bl.get("dofollow") or 0),
            "main_intent": intent.get("main_intent", "unknown"),
            "foreign_intent": foreign_intent or "unknown",
            "images": "images" in serp_types,
            "videos": "video" in serp_types,
            "discussions_and_forums": "discussions_and_forums" in serp_types,
        }

    except Exception as e:
        logger.error(f"Error fetching DataForSEO data for '{keyword}': {e}")
        return {}


async def fetch_dataforseo_backlinks(state: REXT) -> Dict[str, Any]:

    default_backlinks: SERPBacklinks = {
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

    serp_payload = state.get("serp_payload")
    seo_result = state.get("seo_result", {})

    if not serp_payload:
        logger.error("No serp_payload in state")
        return {"seo_result": {"serp_backlinks": default_backlinks}}

    query = serp_payload.get("query", "")
    country = serp_payload.get("country", "")

    if not query:
        logger.error("No query in serp_payload")
        return {"seo_result": {"serp_backlinks": default_backlinks}}

    default_backlinks["keyword"] = query

    user_id = serp_payload.get("user_id")
    workspace_id = serp_payload.get("workspace_id")
    if not user_id or not workspace_id:
        logger.error("Missing user_id or workspace_id")
        return {"seo_result": {"serp_backlinks": default_backlinks}}

    location_name, language_code = resolve_country(country)

    # Deduct serp_seo credit BEFORE the API call — no spend if user can't afford it
    from src.utils.credit_manager import (
        STAGE_CREDITS,
        InsufficientCreditsError,
        _emit_credit_event,
        consume_stage_credits,
    )

    try:
        await consume_stage_credits(user_id, STAGE_CREDITS["serp_seo"], "serp_seo")
    except InsufficientCreditsError as e:
        logger.warning(
            "Insufficient credits for serp_seo: need %d, have %d (user=%s) — skipping DataForSEO call",
            e.required,
            e.available,
            user_id,
        )
        _emit_credit_event(e.available, e.stage, e.required, step="credits.exhausted")
        return {"seo_result": {**seo_result, "serp_backlinks": default_backlinks}}

    logger.info(f"Fetching DataForSEO for '{query}' @ {location_name} ({language_code})")

    data = await get_dataforseo_data(query, location_name, language_code)

    if not data:
        logger.warning(f"No DataForSEO data for '{query}' — using defaults")
        return {"seo_result": {**seo_result, "serp_backlinks": default_backlinks}}

    logger.info(
        f"DataForSEO OK — vol={data['search_volume']} kd={data['keyword_difficulty']} "
        f"intent={data['main_intent']} bl={data['backlinks']} rd={data['referring_domains']}"
    )

    return {"seo_result": {**seo_result, "serp_backlinks": data}}
