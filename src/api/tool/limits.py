"""
Bounds for the public free tools (/api/v1/tools/*), which the rext.ai site's tool pages call from
the visitor's browser without a login.

Per UTC day:
- each visitor (by address) has a number of calls per tool: fewer for a tool that calls a model;
- the tools that call a model share a budget in US dollars (FREE_TOOLS_DAILY_BUDGET_USD). Each
  call is charged its worst case before it runs (its input as often as a prompt can carry it, and
  its output cap, at the model's list price), so the day's real spending stays under the budget
  while Redis is up. During a Redis outage each process counts for itself, with a budget of its
  own: a day with an outage can reach a few times the budget, one for Redis and one per process;
- a model tool's request body is at most MAX_INPUT_BYTES.

A call is counted only once its request is valid (@bounded runs inside the route), and a refused
call counts nothing. It gets 429 (413 for a body that is too long) with a message the site's tool
pages show as they are. Refusals stay out of the admin's Error Logs, except the day's first
refusal for the budget. The counts live in Redis, checked and added in one step.
"""

import functools
import hashlib
import ipaddress
import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, Tuple

from fastapi import HTTPException, Request, status

from src.api.cache.redis_client import cache
from src.api.config import get_settings
from src.api.tool.turnstile import verify_turnstile
from src.utils.ip_allowlist import proxy_trust_is_spoofable
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
# A token is at least one byte, so counting one per byte of input never counts low. A prompt
# carries a request field at most three times (title tags' names the brand three times;
# test_free_tool_limits checks every template), and the prompts' own text adds under 1,000 tokens.
PROMPT_COPIES = 3
PROMPT_TOKENS = 1000

VISITOR_LIMIT_MESSAGE = (
    "You've reached today's limit for this free tool. Please try again tomorrow."
)
BUDGET_MESSAGE = "The free AI tools have reached today's limit. Please try again tomorrow."
TOO_LONG_MESSAGE = "That's too much text for the free tool: about 3,000 words at most."

# One step in Redis: refuse past the visitor's limit (1) or the budget (2), else count both (0).
# KEYS: the visitor's count, the day's spend. ARGV: the visitor's limit, the cost, the budget, the
# seconds the keys live.
TAKE_SCRIPT = """
if tonumber(redis.call('GET', KEYS[1]) or '0') >= tonumber(ARGV[1]) then return 1 end
local cost = tonumber(ARGV[2])
if cost > 0 then
  if tonumber(redis.call('GET', KEYS[2]) or '0') + cost > tonumber(ARGV[3]) then return 2 end
  redis.call('INCRBY', KEYS[2], cost)
  redis.call('EXPIRE', KEYS[2], ARGV[4])
end
redis.call('INCR', KEYS[1])
redis.call('EXPIRE', KEYS[1], ARGV[4])
return 0
"""
TAKEN, VISITOR_LIMIT, BUDGET_LIMIT = 0, 1, 2


def model_tokens(tool: str) -> int:
    """The output cap of a model tool's calls; a tool that runs no model has none."""
    spec = FREE_TOOLS[tool]
    if not spec.model_calls:
        raise KeyError(f"{tool} runs no model")
    return spec.max_tokens


def worst_case_cost(spec: FreeTool, body_bytes: int) -> int:
    """The most one request can cost, in millionths of a dollar."""
    input_tokens = PROMPT_COPIES * body_bytes + PROMPT_TOKENS
    per_call = input_tokens * INPUT_PRICE_PER_MILLION + spec.max_tokens * OUTPUT_PRICE_PER_MILLION
    return math.ceil(per_call * spec.model_calls)


def _today() -> Tuple[str, int]:
    """The UTC day, and the seconds until it ends."""
    now = datetime.now(timezone.utc)
    tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return now.strftime("%Y%m%d"), max(1, math.ceil((tomorrow - now).total_seconds()))


class DayCounts:
    """Counts that last a UTC day: in Redis when it is up, else in this process's memory."""

    def __init__(self) -> None:
        self.memory: Dict[str, int] = {}
        self.memory_day: Optional[str] = None

    async def take(
        self,
        visitor_key: str,
        limit: int,
        spend_key: str,
        cost: int,
        budget: int,
        day: str,
        ttl: int,
    ) -> int:
        """Count one call and its cost, unless either would pass its limit: TAKEN or why not."""
        redis = cache.redis
        if redis is not None:
            try:
                args = (limit, cost, budget, ttl + 60)
                return int(await redis.eval(TAKE_SCRIPT, 2, visitor_key, spend_key, *args))
            except Exception as e:  # noqa: BLE001 - a Redis failure falls back to memory
                logger.debug(f"Free-tool counts in memory, Redis unavailable: {e}")
        if self.memory_day != day:
            self.memory, self.memory_day = {}, day
        # No await between the checks and the counts, so this is one step for the process too.
        if self.memory.get(visitor_key, 0) >= limit:
            return VISITOR_LIMIT
        if cost and self.memory.get(spend_key, 0) + cost > budget:
            return BUDGET_LIMIT
        if cost:
            self.memory[spend_key] = self.memory.get(spend_key, 0) + cost
        self.memory[visitor_key] = self.memory.get(visitor_key, 0) + 1
        return TAKEN


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


def _tool(request: Request) -> str:
    route = request.scope.get("route")
    return getattr(route, "path", request.url.path).rsplit("/tools/", 1)[-1]


def _trusted_address(request: Request) -> Optional[str]:
    """The client address, when the server can trust it: an IP, and a TRUSTED_PROXY_IPS that names
    the proxy (with a catch-all, anyone could send it). Logs nothing: the address is personal data."""
    host = request.client.host if request.client else None
    try:
        ipaddress.ip_address(host or "")
    except ValueError:
        return None
    return None if proxy_trust_is_spoofable(get_settings().TRUSTED_PROXY_IPS) else host


def _visitor(request: Request) -> str:
    """The visitor's address, hashed. An address the server can't trust counts as one visitor: the
    limit fails closed."""
    address = _trusted_address(request) or "unverified"
    return hashlib.sha256(address.encode()).hexdigest()[:16]


async def free_tool_size(request: Request) -> None:
    """The tools router's dependency: a model tool's body is at most MAX_INPUT_BYTES."""
    if FREE_TOOLS.get(_tool(request), FreeTool()).model_calls:
        if len(await request.body()) > MAX_INPUT_BYTES:
            raise _refuse(status.HTTP_413_CONTENT_TOO_LARGE, TOO_LONG_MESSAGE)


async def count_call(request: Request) -> None:
    """Count a valid call against its visitor's limit and the budget, or refuse it."""
    global _budget_logged
    settings = get_settings()
    tool = _tool(request)
    spec = FREE_TOOLS.get(tool, FreeTool())
    day, ttl = _today()
    if spec.model_calls:
        limit = settings.FREE_TOOLS_MODEL_CALLS_PER_DAY
        cost = worst_case_cost(spec, len(await request.body()))
    else:
        limit, cost = settings.FREE_TOOLS_CALLS_PER_DAY, 0
    budget = round(settings.FREE_TOOLS_DAILY_BUDGET_USD * 1_000_000)
    visitor_key = f"freetools:{day}:visitor:{_visitor(request)}:{tool}"
    taken = await COUNTS.take(visitor_key, limit, f"freetools:{day}:spend", cost, budget, day, ttl)
    if taken == VISITOR_LIMIT:
        raise _refuse(status.HTTP_429_TOO_MANY_REQUESTS, VISITOR_LIMIT_MESSAGE, ttl)
    if taken == BUDGET_LIMIT:
        first = _budget_logged != day
        if first:
            _budget_logged = day
            logger.warning(
                "Free AI tools stopped for the day: the "
                f"${settings.FREE_TOOLS_DAILY_BUDGET_USD} budget is used up"
            )
        raise _refuse(status.HTTP_429_TOO_MANY_REQUESTS, BUDGET_MESSAGE, ttl, log=first)


def bounded(endpoint):
    """A free tool's route: counted (count_call) once FastAPI has validated its request, before it
    runs. A dependency would run before the validation, so an invalid request would be charged.
    A model tool's bot check (turnstile.py) comes first, so a refused token counts nothing."""

    @functools.wraps(endpoint)
    async def run(*args, **kwargs):
        request = kwargs["request"]
        if FREE_TOOLS.get(_tool(request), FreeTool()).model_calls:
            await verify_turnstile(request, _trusted_address(request))
        await count_call(request)
        return await endpoint(*args, **kwargs)

    run.free_tool_bounded = True
    return run
