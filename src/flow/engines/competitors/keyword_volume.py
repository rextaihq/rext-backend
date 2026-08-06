"""Filters candidate seed keywords down to the highest search-volume ones via DataForSEO Labs."""
import logging
import os
from typing import Dict, List

import httpx
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

DATAFORSEO_BACKLINKS_URL = os.getenv("DATAFORSEO_BACKLINKS_URL")
AUTH_HEADER = os.getenv("DATAFORSEO_AUTH_HEADER")
DATAFORSEO_TIMEOUT = 45


async def get_keyword_volumes(
    keywords: List[str],
    location_name: str = "United States",
    language_code: str = "en",
) -> Dict[str, int]:
    """Batched search-volume lookup — all candidate keywords in a single DataForSEO call."""
    if not keywords or not DATAFORSEO_BACKLINKS_URL or not AUTH_HEADER:
        return {}

    payload = [{
        "keywords": keywords,
        "location_name": location_name,
        "language_code": language_code,
    }]
    headers = {
        "Authorization": f"Basic {AUTH_HEADER}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=DATAFORSEO_TIMEOUT) as client:
            response = await client.post(DATAFORSEO_BACKLINKS_URL, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()

        items = data["tasks"][0]["result"][0]["items"]
    except Exception as exc:
        logger.warning("Keyword volume lookup failed: %s", exc)
        return {}

    volumes: Dict[str, int] = {}
    for item in items or []:
        kw = item.get("keyword")
        vol = (item.get("keyword_info") or {}).get("search_volume") or 0
        if kw:
            volumes[kw] = vol
    return volumes


async def select_top_keywords_by_volume(
    keywords: List[str],
    top_n: int = 8,
    location_name: str = "United States",
    language_code: str = "en",
) -> List[str]:
    """Rank candidate keywords by real search volume, keep only the top_n highest."""
    volumes = await get_keyword_volumes(keywords, location_name, language_code)
    ranked = sorted(keywords, key=lambda kw: volumes.get(kw, 0), reverse=True)
    top = ranked[:top_n]
    logger.info("Selected top %d keywords by volume: %s", top_n, top)
    return top
