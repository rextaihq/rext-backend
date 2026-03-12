"""
Rate limiter for OpenAI embedding API calls.

Implements per-user and global rate limiting using Redis
to prevent cost overruns and API abuse.
"""

import asyncio
import time
from typing import Optional

import redis.asyncio as aioredis

from src.api.config import get_settings
from src.utils.logger import logger

settings = get_settings()


class EmbeddingRateLimiter:
    """
    Redis-based rate limiter for embedding API calls.

    Uses a sliding window counter pattern to enforce:
    - Per-user limits: Max embedding requests per minute per user
    - Global limits: Max total embedding requests per minute across all users
    """

    def __init__(
        self,
        redis_url: Optional[str] = None,
        user_rpm: int = 10,
        global_rpm: int = 200,
    ):
        """
        Args:
            redis_url: Redis connection URL. Defaults to settings.REDIS_URL.
            user_rpm: Maximum embedding requests per minute per user.
            global_rpm: Maximum embedding requests per minute globally.
        """
        self.redis_url = redis_url or settings.REDIS_URL
        self.user_rpm = user_rpm
        self.global_rpm = global_rpm
        self._redis: Optional[aioredis.Redis] = None

    async def _get_redis(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = aioredis.from_url(self.redis_url, decode_responses=True)
        return self._redis

    async def check_rate_limit(self, user_id: str) -> bool:
        """
        Check if the user is within rate limits.

        Args:
            user_id: The user identifier.

        Returns:
            True if the request is allowed, False if rate limited.
        """
        r = await self._get_redis()
        now = time.time()
        window_start = now - 60  # 1-minute window

        pipe = r.pipeline()

        # Per-user rate limit
        user_key = f"embedding_rate:{user_id}"
        pipe.zremrangebyscore(user_key, 0, window_start)
        pipe.zcard(user_key)

        # Global rate limit
        global_key = "embedding_rate:global"
        pipe.zremrangebyscore(global_key, 0, window_start)
        pipe.zcard(global_key)

        results = await pipe.execute()
        user_count = results[1]
        global_count = results[3]

        if user_count >= self.user_rpm:
            logger.warning(
                f"User {user_id} exceeded embedding rate limit: {user_count}/{self.user_rpm} RPM"
            )
            return False

        if global_count >= self.global_rpm:
            logger.warning(
                f"Global embedding rate limit exceeded: {global_count}/{self.global_rpm} RPM"
            )
            return False

        return True

    async def record_request(self, user_id: str) -> None:
        """Record an embedding request for rate limiting."""
        r = await self._get_redis()
        now = time.time()

        pipe = r.pipeline()

        user_key = f"embedding_rate:{user_id}"
        pipe.zadd(user_key, {f"{now}": now})
        pipe.expire(user_key, 120)

        global_key = "embedding_rate:global"
        pipe.zadd(global_key, {f"{user_id}:{now}": now})
        pipe.expire(global_key, 120)

        await pipe.execute()


# Singleton instance
_rate_limiter: Optional[EmbeddingRateLimiter] = None


def get_embedding_rate_limiter() -> EmbeddingRateLimiter:
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = EmbeddingRateLimiter()
    return _rate_limiter