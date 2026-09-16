"""Batched LLM classification of candidate domains.

Batching mechanics (chunk into groups of CLASSIFY_BATCH_SIZE, run batches
concurrently) are ported verbatim from the reference Colab notebook. The
classification prompt itself is a deliberate deviation from the notebook's
one-line criterion — see classify_batch's docstring for why.
"""

import asyncio
import json
from typing import Dict, Iterator

from src.flow.engines.competitors.constants import CLASSIFY_BATCH_SIZE
from src.flow.engines.competitors.llm_client import call_openai_json


def chunk(lst: list, size: int) -> Iterator[list]:
    for i in range(0, len(lst), size):
        yield lst[i : i + size]


async def classify_batch(business_summary: dict, items: list) -> dict:
    """Classify candidate domains as direct competitors or not."""
    normalized_items = [
        {"domain": x, "title": "", "snippet": ""} if isinstance(x, str) else x for x in items
    ]
    domains = [it["domain"] for it in normalized_items]

    prompt = f"""Reference business (JSON): {json.dumps(business_summary)}

Candidate companies to evaluate:
{json.dumps(normalized_items, indent=2)}

For each candidate domain, decide if it is a DIRECT competitor of the reference business.

A domain is a DIRECT competitor ONLY if ALL 4 of the following hold:
1. SAME SPECIFIC NICHE & INDUSTRY — it offers the same or directly competing products/services in the same market sector.
2. COMPATIBLE BUSINESS MODEL — agency vs. self-serve SaaS vs. plugin/software tool vs. hosting vs. content/media site vs. equipment dealer must be logically comparable:
   - Educational/content sites: software tools, themes, and hosting are NEVER direct competitors (is_competitor=false, confidence <= 0.1).
   - Service agencies: self-serve plugins are NOT direct competitors.
   - Software/SaaS platforms: blogs, directories, review sites, and comparison listicles are NOT direct competitors (is_competitor=false, confidence <= 0.1).
   - Standards organizations & non-profit councils: compliance audit services, security certification platforms, and framework automation tools ARE valid direct competitors in that ecosystem (is_competitor=true, confidence 0.70-0.90).
   - Machinery/Equipment dealerships: other commercial equipment dealerships and machinery seller networks are direct competitors.
3. SAME TARGET CUSTOMER & COMPARABLE SCALE — a buyer or user would realistically evaluate both for the exact same decision. Mega-scale generalists (e.g. Microsoft, Google, Salesforce) are NOT direct competitors for small/specialized firms unless the reference business operates at that scale.
4. NOT a supplier, partner, tool, plugin, or platform that the reference business uses or builds on. (Exception: competing dealer networks selling the same manufacturer line are competitors).

CRITICAL RULES:
- NEVER classify document sharing platforms, PDF repositories, digital libraries (e.g. Scribd, SlideShare, Issuu, PDFCoffee, Academia.edu), or file upload portals as competitors (always is_competitor=false, confidence=0.0).
- NEVER classify the reference business itself, its alternate TLDs (.com/.net/.io), sister sites, or brand variations as a competitor (is_competitor=false, confidence=0.0).
- Review sites, product roundups, tool directories, and curated listicles are publications, NEVER competitors.

Return ONLY a JSON object mapping each domain name to an object with:
- "is_competitor": true/false
- "confidence": 0-1 float. If it meets all criteria, assign 0.75 - 1.0. If it fails any criterion, is_competitor must be false and confidence 0.0 - 0.3.
- "reason": one short sentence explaining the decision.
"""
    try:
        return await call_openai_json(prompt, max_tokens=1200)
    except Exception:
        return {
            d: {"is_competitor": False, "confidence": 0.0, "reason": "classification failed"}
            for d in domains
        }


async def classify_all(business_summary: dict, candidates: Dict[str, dict]) -> dict:
    items = [
        {
            "domain": d,
            "title": ev.get("title", ""),
            "snippet": ev.get("snippet", ""),
        }
        for d, ev in candidates.items()
    ]
    batches = list(chunk(items, CLASSIFY_BATCH_SIZE))
    results = await asyncio.gather(*[classify_batch(business_summary, b) for b in batches])
    merged = {}
    for batch_result in results:
        merged.update(batch_result)
    return merged
