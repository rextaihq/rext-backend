"""A shared day-long cache of a keyword's SERP and of its intent classification (rext-control#697).

A keyword's search results for a country are the same for every user within a day, and the
intent call reads only the keyword and those results. The live SERP is most of the analysis
step (15 to 30 seconds measured), and the intent call most of the rest, so a re-analysis, a
Library start or another user's run on the same keyword reuses both. Only a successful lookup
is kept. Credits are charged as before: the cache saves time and the providers' cost, not
the user's credits.

Redis holds it, through the main loop as every node's I/O does here; when Redis is down or
off, every lookup misses and the run goes live as before.
"""

import hashlib
import json
import logging
from typing import Any, Optional

from src.utils.loop_bridge import run_on_main_loop

logger = logging.getLogger(__name__)

CACHE_TTL_SECONDS = 24 * 60 * 60
# Bumped when what's cached changes shape, so an older entry is never read as a newer one.
_VERSION = "v1"


def _digest(*parts: Any) -> str:
    raw = json.dumps(parts, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _normal(query: str) -> str:
    return " ".join((query or "").lower().split())


def serp_key(query: str, country: Optional[str], language: str = "en") -> str:
    """The cache key of a keyword's SERP: the keyword as typed, any case or spacing."""
    return f"serp:{_VERSION}:{_digest(_normal(query), country or 'global', language)}"


def intent_key(query: str, domain_groups: dict) -> str:
    """The cache key of an intent classification: the keyword and the very rows it reads."""
    return f"serp_intent:{_VERSION}:{_digest(_normal(query), domain_groups)}"


async def read(key: str) -> Optional[Any]:
    """The cached value, or None (a miss, Redis off or failing)."""
    from src.api.cache.redis_client import cache

    if not cache.is_enabled:
        return None
    try:
        return await run_on_main_loop(cache.get(key))
    except Exception as e:  # noqa: BLE001 - a cache that fails is a miss
        logger.warning(f"SERP cache read failed ({type(e).__name__}); going live")
        return None


async def write(key: str, value: Any) -> None:
    """Keep a value for a day; a failure only means the next run goes live."""
    from src.api.cache.redis_client import cache

    if not cache.is_enabled:
        return
    try:
        await run_on_main_loop(cache.set(key, value, ttl=CACHE_TTL_SECONDS))
    except Exception as e:  # noqa: BLE001 - a cache that fails is a miss
        logger.warning(f"SERP cache write failed ({type(e).__name__})")
