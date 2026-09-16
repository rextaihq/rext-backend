"""OpenAI JSON-mode helpers + business-summary/query-generation prompts.

Ported verbatim from the reference Colab notebook. Uses the openai SDK directly
(response_format={"type": "json_object"} + manual json.loads) rather than
LangChain's structured-output path, to match the notebook's actual call/parse
behavior exactly.
"""

import json
import logging

from openai import AsyncOpenAI

from src.api.config import settings
from src.flow.engines.competitors.constants import OPENAI_MODEL

logger = logging.getLogger(__name__)

_client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)


async def call_openai_json(prompt: str, max_tokens: int = 512) -> dict:
    """Calls OpenAI in JSON mode and parses the response."""
    resp = await _client.chat.completions.create(
        model=OPENAI_MODEL,
        max_tokens=max_tokens,
        response_format={"type": "json_object"},
        messages=[{"role": "user", "content": prompt}],
    )
    text = resp.choices[0].message.content
    return json.loads(text)


async def call_openai_json_array(prompt: str, max_tokens: int = 512) -> list:
    """Same as above but for prompts whose natural output is a JSON array — wraps/unwraps
    since OpenAI JSON mode requires a top-level object."""
    wrapped_prompt = prompt + '\n\nReturn ONLY a JSON object of the form {"items": [...]}.'
    resp = await _client.chat.completions.create(
        model=OPENAI_MODEL,
        max_tokens=max_tokens,
        response_format={"type": "json_object"},
        messages=[{"role": "user", "content": wrapped_prompt}],
    )
    text = resp.choices[0].message.content
    parsed = json.loads(text)
    return parsed.get("items", []) if isinstance(parsed, dict) else parsed


async def summarize_business(site_url: str, pages: dict) -> dict:
    combined = "\n\n".join(f"URL: {u}\n{txt}" for u, txt in pages.items())[:3500]
    prompt = f"""You are looking at scraped text from a company website ({site_url}).

{combined}

Return ONLY a JSON object with these fields:
- "company_name": best-guess brand/company name
- "category": the SPECIFIC, established market category a buyer or industry analyst
  would actually use for this business — not a generic literal description of what
  it does. Base it on the specific features/offerings described, and prefer the term
  real competitors or review sites (G2, Capterra, etc.) would use for this exact
  space over a broader umbrella term. E.g. "headless CMS" (not "content management
  tool" or "app framework" — schema/content modeling + admin panel + media library
  is headless-CMS language even if the marketing copy says "framework"),
  "WordPress maintenance service" (not "website support"), "enterprise WordPress
  development agency" (not "web development"), "project management software"
  (not "productivity tool").
- "offerings": array of 2-5 short strings describing core products/services
- "target_audience": short string, who this is for
- "keywords": array of 5-8 keywords/phrases people might search when looking for this category
"""
    return await call_openai_json(prompt)


async def generate_queries(summary: dict) -> dict:
    prompt = f"""Business summary (JSON): {json.dumps(summary)}

Generate SERP search queries to find this company's DIRECT competitors.
Return ONLY a JSON object:
- "category_queries": 4 short search-engine-style queries a buyer would type to find
  companies like this one. Vary phrasing across styles, e.g. "best {{category}}",
  "{{category}} for {{target_audience}}", "open source {{category}}", "top {{category}} tools".
  Do NOT include the company's own name.
- "brand_queries": exactly 5 queries to find comparison coverage for this company.
  Use ALL of these patterns (replace {{company_name}} with the actual company_name):
  1. "{{company_name}} alternatives"
  2. "{{company_name}} vs"
  3. "{{company_name}} competitors"
  4. "tools like {{company_name}}"
  5. "site:alternativeto.net OR site:stackshare.io {{company_name}}"
     (catches niche/early-stage products not yet listed on G2 or Capterra)

Keep every query under 10 words.
"""
    return await call_openai_json(prompt)
