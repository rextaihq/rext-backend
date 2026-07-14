"""
Rate limiter for Google Search Console URL Inspection API calls.

Google enforces a per-property quota on the URL Inspection API (commonly
~2,000/day and ~600/min at time of writing — verify current limits in the
Search Console API quota dashboard, since Google can change these; the
defaults here are intentionally conservative and configurable via
src/config/google_config.py rather than hardcoded).

The per-minute check reuses the same Redis sliding-window sorted-set
technique as EmbeddingRateLimiter (src/utils/embedding_rate_limiter.py). The
per-day check is new: a simple UTC-date-stamped counter with TTL, since a
sliding window isn't needed for a calendar-day quota.
"""

import time
from datetime import datetime, timezone
from typing import Optional

import redis.asyncio as aioredis

from src.api.config import get_settings
from src.utils.logger import logger

settings = get_settings()

_MINUTE_WINDOW_SECONDS = 60
_DAILY_KEY_TTL_SECONDS = 172800  # 2 days safety margin


class GoogleQuotaLimiter:
    """Redis-based per-minute + per-day quota limiter, keyed per Search Console property."""

    def __init__(
        self,
        redis_url: Optional[str] = None,
        per_minute_limit: int = 300,
        per_day_limit: int = 200,
    ):
        self.redis_url = redis_url or settings.REDIS_URL
        self.per_minute_limit = per_minute_limit
        self.per_day_limit = per_day_limit
        self._redis: Optional[aioredis.Redis] = None

    async def _get_redis(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = aioredis.from_url(self.redis_url, decode_responses=True)
        return self._redis

    async def try_reserve(self, site_key: str) -> bool:
        """
        Check both the per-minute and per-day quota for a site, and if both
        have room, record this call and return True. Returns False (without
        recording) if either limit is currently exceeded.
        """
        r = await self._get_redis()

        if not await self._check_minute_limit(r, site_key):
            return False

        if not await self._check_and_increment_daily_limit(r, site_key):
            return False

        await self._record_minute_call(r, site_key)
        return True

    async def _check_minute_limit(self, r: aioredis.Redis, site_key: str) -> bool:
        now = time.time()
        window_start = now - _MINUTE_WINDOW_SECONDS
        minute_key = f"google_url_inspection_rate:{site_key}"

        pipe = r.pipeline()
        pipe.zremrangebyscore(minute_key, 0, window_start)
        pipe.zcard(minute_key)
        results = await pipe.execute()
        count = results[1]

        if count >= self.per_minute_limit:
            logger.warning(
                f"[GoogleQuota] Per-minute limit hit for {site_key}: {count}/{self.per_minute_limit}"
            )
            return False
        return True

    async def _record_minute_call(self, r: aioredis.Redis, site_key: str) -> None:
        now = time.time()
        minute_key = f"google_url_inspection_rate:{site_key}"

        pipe = r.pipeline()
        pipe.zadd(minute_key, {f"{now}": now})
        pipe.expire(minute_key, _MINUTE_WINDOW_SECONDS * 2)
        await pipe.execute()

    async def _check_and_increment_daily_limit(self, r: aioredis.Redis, site_key: str) -> bool:
        today = datetime.now(timezone.utc).date().isoformat()
        daily_key = f"google_url_inspection_daily:{site_key}:{today}"

        count = await r.incr(daily_key)
        if count == 1:
            await r.expire(daily_key, _DAILY_KEY_TTL_SECONDS)

        if count > self.per_day_limit:
            logger.warning(
                f"[GoogleQuota] Daily limit hit for {site_key}: {count}/{self.per_day_limit}"
            )
            return False
        return True


_quota_limiter: Optional[GoogleQuotaLimiter] = None


def get_google_quota_limiter() -> GoogleQuotaLimiter:
    global _quota_limiter
    if _quota_limiter is None:
        from src.config.google_config import google_config

        _quota_limiter = GoogleQuotaLimiter(
            per_minute_limit=google_config.GOOGLE_INDEX_INSPECTION_PER_MINUTE_LIMIT,
            per_day_limit=google_config.GOOGLE_INDEX_INSPECTION_DAILY_QUOTA_PER_SITE,
        )
    return _quota_limiter
