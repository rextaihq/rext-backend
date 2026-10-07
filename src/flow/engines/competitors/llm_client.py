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
from src.utils.loop_local_http import SHARED_ASYNC_CLIENT

logger = logging.getLogger(__name__)

# The shared client keeps one connection pool per event loop, so runs on their own loops never
# share a connection (G80).
_client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY, http_client=SHARED_ASYNC_CLIENT)


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

Generate SERP search queries to find this company's DIRECT competitors across any market/industry.
Return ONLY a JSON object:
- "category_queries": 5 short, highly diverse search-engine-style queries a buyer would type to find direct competitors or alternative solutions.
  Vary search terms across keywords, offerings, and search intents (e.g. combining different core services, key capabilities, target audience, or industry terms from the summary).
  Do NOT repeat the exact same category string across queries; use natural variations (e.g., "AI writing tools", "SEO content generators", "AI copywriting platform").
  Do NOT include the company's own name in category_queries.
- "brand_queries": 5 queries to find direct alternatives and comparison articles for this company:
  1. "{summary.get("company_name", "")} alternatives"
  2. "{summary.get("company_name", "")} competitors"
  3. "{summary.get("company_name", "")} vs"
  4. "companies like {summary.get("company_name", "")}"
  5. "top alternatives to {summary.get("company_name", "")}"

Keep every query under 10 words.
"""
    return await call_openai_json(prompt)
