"""DataForSEO SERP search, ported from the reference Colab notebook.

Reuses the application's already-configured DATAFORSEO_SERP_URL / DATAFORSEO_AUTH_HEADER
env vars (same ones read by src/flow/engines/serp/fetch_serp.py) rather than any
notebook-hardcoded credential. Uses httpx instead of aiohttp — see scraping.py docstring.
"""

import asyncio
import logging
import os
from typing import List

import httpx
from dotenv import load_dotenv

from src.flow.engines.competitors.constants import (
    CONCURRENCY,
    MAX_ORGANIC_PER_QUERY,
    REQUEST_TIMEOUT,
    SERP_LANGUAGE_CODE,
    SERP_LOCATION_CODE,
)

load_dotenv()

logger = logging.getLogger(__name__)

DATAFORSEO_SERP_URL = os.getenv("DATAFORSEO_SERP_URL")
DATAFORSEO_AUTH_HEADER = os.getenv("DATAFORSEO_AUTH_HEADER")


def configuration_error() -> str | None:
    """Return a safe, user-actionable reason when search cannot run.

    Never include credential values in logs or SSE payloads.
    """
    missing = []
    if not DATAFORSEO_SERP_URL:
        missing.append("DATAFORSEO_SERP_URL")
    if not DATAFORSEO_AUTH_HEADER:
        missing.append("DATAFORSEO_AUTH_HEADER")
    if missing:
        return f"Competitor search is unavailable: missing {', '.join(missing)}"
    return None


async def serp_search(client: httpx.AsyncClient, query: str, sem: asyncio.Semaphore) -> List[dict]:
    if error := configuration_error():
        logger.warning("%s; skipping search for %r", error, query)
        return []

    payload = [
        {
            "keyword": query,
            "language_code": SERP_LANGUAGE_CODE,
            "location_code": SERP_LOCATION_CODE,
            "depth": MAX_ORGANIC_PER_QUERY,
        }
    ]
    headers = {
        "Authorization": f"Basic {DATAFORSEO_AUTH_HEADER}",
        "Content-Type": "application/json",
    }

    try:
        async with sem:
            resp = await client.post(
                DATAFORSEO_SERP_URL,
                headers=headers,
                json=payload,
                timeout=REQUEST_TIMEOUT,
            )
            data = resp.json()
    except Exception as exc:
        logger.warning("SERP search failed for %r: %s", query, exc)
        return []

    results = []
    try:
        tasks = data.get("tasks", [])
        if not tasks or not tasks[0].get("result"):
            return []
        items = tasks[0]["result"][0].get("items", []) or []
        for item in items:
            if item.get("type") != "organic":
                continue
            results.append(
                {
                    "query": query,
                    "title": item.get("title", "") or "",
                    "link": item.get("url", "") or "",
                    "snippet": item.get("description", "") or "",
                }
            )
    except Exception as exc:
        logger.warning("SERP response parsing failed for %r: %s", query, exc)
        return []
    return results[:MAX_ORGANIC_PER_QUERY]


async def run_all_searches(queries: List[str]) -> List[dict]:
    sem = asyncio.Semaphore(CONCURRENCY)
    async with httpx.AsyncClient() as client:
        results = await asyncio.gather(*[serp_search(client, q, sem) for q in queries])
    return [r for batch in results for r in batch]
