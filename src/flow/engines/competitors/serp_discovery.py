"""Runs SERP searches for each seed keyword and aggregates which domains repeat across results."""
import logging
import os
from collections import defaultdict
from typing import Any, Dict, List

import httpx
from dotenv import load_dotenv

from src.flow.engines.competitors.domain_utils import get_root_domain

load_dotenv()

logger = logging.getLogger(__name__)

DATAFORSEO_SERP_URL = os.getenv("DATAFORSEO_SERP_URL")
AUTH_HEADER = os.getenv("DATAFORSEO_AUTH_HEADER")
REQUEST_TIMEOUT = 45


async def run_serp_search(
    keyword: str,
    location_name: str = "United States",
    language_code: str = "en",
    num_results: int = 10,
) -> List[str]:
    """Returns organic result URLs for a keyword. Empty list on any failure."""
    if not DATAFORSEO_SERP_URL or not AUTH_HEADER:
        logger.warning("DataForSEO SERP env vars not configured — skipping search for %r", keyword)
        return []

    payload = [{
        "keyword": keyword,
        "location_name": location_name,
        "language_code": language_code,
        "device": "desktop",
        "os": "windows",
        "depth": num_results,
    }]
    headers = {
        "Authorization": f"Basic {AUTH_HEADER}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            response = await client.post(DATAFORSEO_SERP_URL, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()

        tasks = data.get("tasks", [])
        if not tasks or tasks[0].get("status_code") != 20000:
            logger.warning(
                "DataForSEO task error for %r: %s",
                keyword, tasks[0].get("status_message") if tasks else "no tasks returned",
            )
            return []

        result = tasks[0].get("result") or []
        if not result:
            return []

        items = result[0].get("items") or []
        urls = []
        for item in items:
            if item.get("type") == "organic" and item.get("url"):
                urls.append(item["url"])
            if len(urls) >= num_results:
                break
        return urls
    except Exception as exc:
        logger.warning("SERP search failed for %r: %s", keyword, exc)
        return []


def aggregate_domains(keyword_results: Dict[str, List[str]], own_domain: str) -> Dict[str, dict]:
    """Group SERP result URLs by root domain, excluding the workspace's own domain."""
    own_root = get_root_domain(own_domain)
    domain_data: Dict[str, dict] = defaultdict(
        lambda: {"serp_appearances": 0, "keywords_matched": set(), "sample_urls": []}
    )

    for keyword, urls in keyword_results.items():
        for url in urls:
            root = get_root_domain(url)
            if root == own_root:
                continue
            entry = domain_data[root]
            entry["serp_appearances"] += 1
            entry["keywords_matched"].add(keyword)
            if len(entry["sample_urls"]) < 3:
                entry["sample_urls"].append(url)

    total_keywords = len(keyword_results) or 1
    for root, entry in domain_data.items():
        entry["keyword_overlap_pct"] = round(100 * len(entry["keywords_matched"]) / total_keywords, 1)
        entry["keywords_matched"] = sorted(entry["keywords_matched"])

    return dict(domain_data)
