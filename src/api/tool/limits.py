"""
Bounds for the public free tools (/api/v1/tools/*), which the rext.ai site's tool pages call from
the visitor's browser without a login.

Per UTC day:
- each visitor (by address) has a number of calls per tool: fewer for a tool that calls a model;
- the tools that call a model share a budget in US dollars (FREE_TOOLS_DAILY_BUDGET_USD). Each
  call is charged its worst case before it runs (its whole input and its output cap, at the
  model's list price), so the day's real spending stays under the budget;
- a model tool's request body is at most MAX_INPUT_BYTES.

A refused call gets 429 (413 for a body that is too long) with a message the site's tool pages
show as they are. Refusals stay out of the admin's Error Logs, except the day's first refusal for
the budget. The counts live in Redis; while Redis is down, each process counts for itself.
"""

import hashlib
import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, Tuple

from fastapi import HTTPException, Request, status

from src.api.cache.redis_client import cache
from src.api.config import get_settings
from src.utils.logger import logger


@dataclass(frozen=True)
class FreeTool:
    model_calls: int = 0  # model calls one request can make
    max_tokens: int = 0  # the output cap of each call


# Every POST route of the tools router, by its path under /tools/. tools.py builds each model with
# this max_tokens, so the charge below and the model's real cap are one number. A tool here
# without model calls runs no model.
FREE_TOOLS: Dict[str, FreeTool] = {
    "count_metrics": FreeTool(),
    "meta-description/generate": FreeTool(1, 512),
    "title-tags": FreeTool(3, 512),  # up to two more calls when titles miss 50-60 characters
    "schema-generator": FreeTool(),
    "readability-checker": FreeTool(),
    "canonical-tag-generator": FreeTool(),
    "question-generator": FreeTool(1, 1024),
    "link-checker": FreeTool(),
    "content-idea-generator": FreeTool(1, 2048),
    "robots-txt/generate": FreeTool(),
    "grammar-checker": FreeTool(1, 8192),  # returns the whole corrected text
    "hook-generator": FreeTool(1, 1024),
    "seo-blog-titles": FreeTool(1, 1024),
    "outline-generator": FreeTool(1, 4096),
    "headline-analyzer": FreeTool(1, 1024),
    "hreflang-generator": FreeTool(),
    "keyword-density": FreeTool(),
    "paragraph-rewriter": FreeTool(1, 8192),
    "serp-preview": FreeTool(),
    "sitemap-generator": FreeTool(),
}

# About 3,000 words of English: the grammar checker returns the whole text, within its output cap.
MAX_INPUT_BYTES = 20_000
# gpt-4o-mini's list price, in US dollars per million tokens.
INPUT_PRICE_PER_MILLION = 0.15
OUTPUT_PRICE_PER_MILLION = 0.60
# A token is about four bytes of English; three counts high. The prompts add a few hundred tokens.
BYTES_PER_TOKEN = 3
PROMPT_TOKENS = 1000

VISITOR_LIMIT_MESSAGE = (
    "You've reached today's limit for this free tool. Please try again tomorrow."
)
BUDGET_MESSAGE = "The free AI tools have reached today's limit. Please try again tomorrow."
TOO_LONG_MESSAGE = (
    f"That's too much text for the free tool: up to {MAX_INPUT_BYTES:,} characters"
    " (about 3,000 words)."
)


def model_tokens(tool: str) -> int:
    """The output cap of a model tool's calls; a tool that runs no model has none."""
    spec = FREE_TOOLS[tool]
    if not spec.model_calls:
        raise KeyError(f"{tool} runs no model")
    return spec.max_tokens


def worst_case_cost(spec: FreeTool, body_bytes: int) -> int:
    """The most one request can cost, in millionths of a dollar."""
    input_tokens = body_bytes / BYTES_PER_TOKEN + PROMPT_TOKENS
    per_call = input_tokens * INPUT_PRICE_PER_MILLION + spec.max_tokens * OUTPUT_PRICE_PER_MILLION
    return math.ceil(per_call * spec.model_calls)


def _today() -> Tuple[str, int]:
    """The UTC day, and the seconds until it ends."""
    now = datetime.now(timezone.utc)
    tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return now.strftime("%Y%m%d"), max(1, math.ceil((tomorrow - now).total_seconds()))


class DayCounts:
    """Counters that last a UTC day: in Redis when it is up, else in this process's memory."""

    def __init__(self) -> None:
        self.memory: Dict[str, int] = {}
        self.memory_day: Optional[str] = None

    async def add(self, key: str, amount: int, day: str, ttl: int) -> int:
        redis = cache.redis
        if redis is not None:
            try:
                pipe = redis.pipeline()
                pipe.incrby(key, amount)
                pipe.expire(key, ttl + 60)
                value, _ = await pipe.execute()
                return int(value)
            except Exception as e:  # noqa: BLE001 - a Redis failure falls back to memory
                logger.debug(f"Free-tool counts in memory, Redis unavailable: {e}")
        if self.memory_day != day:
            self.memory, self.memory_day = {}, day
        self.memory[key] = self.memory.get(key, 0) + amount
        return self.memory[key]


COUNTS = DayCounts()
_budget_logged: Optional[str] = None


def _refuse(
    status_code: int, message: str, retry_after: Optional[int] = None, log: bool = False
) -> HTTPException:
    headers = {"Retry-After": str(retry_after)} if retry_after else None
    exc = HTTPException(status_code=status_code, detail=message, headers=headers)
    # A refusal is the limit working, not an error: one Error Logs row each would be a database
    # write for every call a visitor makes past it.
    exc.suppress_error_log = not log
    return exc


async def free_tool_limit(request: Request) -> None:
    """The tools router's dependency: refuse a call past its visitor's limit or the budget."""
    global _budget_logged
    settings = get_settings()
    route = request.scope.get("route")
    tool = getattr(route, "path", request.url.path).rsplit("/tools/", 1)[-1]
    spec = FREE_TOOLS.get(tool, FreeTool())
    body = await request.body() if spec.model_calls else b""
    if len(body) > MAX_INPUT_BYTES:
        raise _refuse(status.HTTP_413_CONTENT_TOO_LARGE, TOO_LONG_MESSAGE)

    day, ttl = _today()
    address = request.client.host if request.client else "unknown"
    visitor = hashlib.sha256(address.encode()).hexdigest()[:16]
    limit = (
        settings.FREE_TOOLS_MODEL_CALLS_PER_DAY
        if spec.model_calls
        else settings.FREE_TOOLS_CALLS_PER_DAY
    )
    visitor_key = f"freetools:{day}:visitor:{visitor}:{tool}"
    if await COUNTS.add(visitor_key, 1, day, ttl) > limit:
        raise _refuse(status.HTTP_429_TOO_MANY_REQUESTS, VISITOR_LIMIT_MESSAGE, ttl)
    if not spec.model_calls:
        return

    cost = worst_case_cost(spec, len(body))
    budget = round(settings.FREE_TOOLS_DAILY_BUDGET_USD * 1_000_000)
    if await COUNTS.add(f"freetools:{day}:spend", cost, day, ttl) > budget:
        # Both are given back: a refused call spends nothing and doesn't count for the visitor.
        await COUNTS.add(f"freetools:{day}:spend", -cost, day, ttl)
        await COUNTS.add(visitor_key, -1, day, ttl)
        first = _budget_logged != day
        if first:
            _budget_logged = day
            logger.warning(
                "Free AI tools stopped for the day: the "
                f"${settings.FREE_TOOLS_DAILY_BUDGET_USD} budget is used up"
            )
        raise _refuse(status.HTTP_429_TOO_MANY_REQUESTS, BUDGET_MESSAGE, ttl, log=first)
