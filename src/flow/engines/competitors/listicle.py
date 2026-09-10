"""Listicle/comparison-page mining, ported verbatim from the reference Colab notebook.

For results that land on known review/listicle domains (G2, Capterra, "best X" pages),
fetch the page and ask an LLM to pull out the actual competitor names/links mentioned —
usually the single highest-precision source of competitor names in the whole pipeline.
"""

import asyncio
import logging

import httpx
from bs4 import BeautifulSoup

from src.flow.engines.competitors.constants import (
    CONCURRENCY,
    LISTICLE_DOMAINS,
    MAX_LISTICLES_TO_MINE,
)
from src.flow.engines.competitors.domain_utils import normalize_domain
from src.flow.engines.competitors.llm_client import call_openai_json_array
from src.flow.engines.competitors.scraping import USER_AGENT, fetch, visible_text

logger = logging.getLogger(__name__)


def is_listicle_result(result: dict) -> bool:
    domain = normalize_domain(result["link"])
    title = result["title"].lower()
    return domain in LISTICLE_DOMAINS or any(
        kw in title for kw in ("alternatives", " vs ", "best ", "top 10", "top ten")
    )


async def mine_listicle(client: httpx.AsyncClient, result: dict, sem: asyncio.Semaphore) -> list:
    html = await fetch(client, result["link"], sem)
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    page_domain = normalize_domain(result["link"]).lower()
    outbound = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.startswith("http"):
            d = normalize_domain(href).lower()
            if d and d != page_domain:
                outbound.add(d)
    text = visible_text(html, max_chars=4000)
    prompt = f"""This is text scraped from a "best tools" / comparison page ({result["link"]}):

{text}

Candidate outbound domains found on this page: {sorted(outbound)[:40]}

Which of those candidate domains are actually named as products/companies being
compared or recommended on this page (not ads, nav links, social icons, or the
listicle site's own footer links)? Max 15 items.
"""
    try:
        named = await call_openai_json_array(prompt)
    except Exception as exc:
        logger.warning("Listicle classification failed for %s: %s", result["link"], exc)
        return []

    # Defensive fix (not in the reference notebook): the LLM sometimes echoes
    # back a shortened form of a candidate domain (e.g. "squarespace" instead
    # of "squarespace.com"), which silently defeats exact-string domain
    # blocklists/matching downstream. Only accept answers that exactly match
    # one of the candidates it was actually given.
    return [d for d in named if str(d).lower().strip() in outbound]


async def mine_all_listicles(results: list) -> list:
    listicle_results = [r for r in results if is_listicle_result(r)][:MAX_LISTICLES_TO_MINE]
    if not listicle_results:
        return []
    sem = asyncio.Semaphore(CONCURRENCY)
    headers = {"User-Agent": USER_AGENT}
    async with httpx.AsyncClient(headers=headers, verify=False, follow_redirects=True) as client:
        mined = await asyncio.gather(*[mine_listicle(client, r, sem) for r in listicle_results])
    return [d for batch in mined for d in batch]
