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


async def classify_batch(business_summary: dict, domains: List[str]) -> dict:
    """Classify each domain as a direct competitor or not.

    Deviation from the reference notebook: the notebook's own classification
    criterion is one generic sentence ("similar core product/service, not a
    related tool/news site/marketplace"), which in practice produced
    confidence scores that didn't reliably track actual directness (e.g.
    microsoft.com scoring ~0.9 "direct competitor" for a small IT
    consultancy). This prompt adds explicit, checkable criteria so
    is_competitor/confidence are trustworthy enough to threshold on
    downstream (see pipeline.py::select_display_competitors).
    """
    prompt = f"""Reference business (JSON): {json.dumps(business_summary)}

For each domain below, decide if it is a DIRECT competitor of the reference business.

A domain is a DIRECT competitor ONLY if ALL of the following hold:
1. SAME SPECIFIC NICHE — it offers the same specific product/service at the same
   level of specialization, not just the same broad industry/topic. ("Custom
   WordPress development agency for SaaS companies" is a specific niche;
   "software" alone is not.)
2. SAME BUSINESS MODEL — e.g. agency vs. self-serve SaaS vs. marketplace vs.
   content/media site must match. A platform, directory, marketplace, or
   publication that merely covers or ranks for the topic is NOT a direct
   competitor, even if it ranks for the same searches.
3. SAME TARGET CUSTOMER & COMPARABLE SCALE — a buyer would realistically
   evaluate both for the exact same purchase decision. A small/specialized
   firm and a mega-scale generalist (e.g. Microsoft, Google, Salesforce) are
   usually NOT direct competitors of each other even when offerings overlap
   on paper, unless the reference business itself operates at that same
   scale.
4. NOT a supplier, partner, tool, or platform that the reference business is
   built on, integrates with, or sells through.

If ANY of these fail, it is NOT a direct competitor — regardless of surface-level
topic overlap.

Domains: {domains}

Return ONLY a JSON object mapping each domain to an object with:
- "is_competitor": true/false
- "confidence": 0-1 float — your confidence in the full DIRECT-competitor judgment
  above (all 4 criteria), not just general topical relevance
- "reason": one short sentence
"""
    try:
        return await call_openai_json(prompt, max_tokens=2500)
    except Exception:
        return {
            d: {"is_competitor": False, "confidence": 0.0, "reason": "classification failed"}
            for d in domains
        }


async def classify_all(business_summary: dict, candidates: Dict[str, dict]) -> dict:
    domain_list = list(candidates.keys())
    batches = list(chunk(domain_list, CLASSIFY_BATCH_SIZE))
    results = await asyncio.gather(*[classify_batch(business_summary, b) for b in batches])
    merged = {}
    for batch_result in results:
        merged.update(batch_result)
    return merged
