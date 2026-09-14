"""Batched LLM classification of candidate domains.

Batching mechanics (chunk into groups of CLASSIFY_BATCH_SIZE, run batches
concurrently) are ported verbatim from the reference Colab notebook. The
classification prompt itself is a deliberate deviation from the notebook's
one-line criterion — see classify_batch's docstring for why.
"""

import asyncio
import json
from typing import Dict, Iterator, List

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
1. SAME SPECIFIC NICHE — it offers the same specific product/service at the same
   level of specialization, not just the same broad industry/topic. ("Custom
   WordPress development agency for SaaS companies" is a specific niche;
   "software" alone is not.)
2. SAME BUSINESS MODEL — agency vs. self-serve SaaS vs. plugin/software tool vs. hosting vs.
   content/media/tutorial site vs. equipment dealer must match:
   - If the reference business is an educational, tutorial, or content/media site, software tools, plugins,
     themes/builders (e.g. Thrive Themes, SeedProd, Beaver Builder), and hosting providers are NEVER direct competitors (is_competitor=false, confidence <= 0.1).
   - If the reference business is a service agency, self-serve software tools or plugins are NOT direct competitors.
   - If the reference business is a software/SaaS platform, blogs, directories, and review sites (e.g. comparison blogs, emailvendorselection, listicles) are NOT direct competitors (is_competitor=false, confidence <= 0.1).
   - If the reference business is an equipment dealer/distributor, general manufacturers or repair blogs are NOT direct competitors.
3. SAME TARGET CUSTOMER & COMPARABLE SCALE — a buyer or user would realistically
   evaluate both for the exact same decision. A small/specialized firm and a mega-scale generalist
   (e.g. Microsoft, Google, Salesforce) are NOT direct competitors unless the reference business
   itself operates at that same scale.
4. NOT a supplier, partner, tool, plugin, theme, or hosting platform that the reference business
   is built on, integrates with, uses, or sells through.

CRITICAL RULES:
- NEVER classify the reference business itself, its alternate domains (e.g. .com vs .net vs .io), sister sites, or domains sharing the company/brand name as a competitor. A business can NEVER compete against itself (always mark is_competitor=false, confidence=0.0).
- Review sites, product roundups, tool directories, and curated listicles are publications, NEVER competitors to software or service businesses.
- If a candidate's title or snippet indicates it is a directory, review blog, or platform, mark is_competitor=false.

Return ONLY a JSON object mapping each domain name to an object with:
- "is_competitor": true/false
- "confidence": 0-1 float. If it strictly meets ALL 4 criteria, assign 0.80 - 1.0. If it fails ANY criterion, is_competitor must be false and confidence must be 0.0 - 0.3.
- "reason": one short sentence explaining the decision based on its offerings and niche.
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
