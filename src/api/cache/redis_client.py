"""
Redis client wrapper for caching.

Provides async Redis operations with connection pooling and error handling.
"""
import json
import time
from typing import Optional, Any
from redis import asyncio as aioredis
from redis.asyncio import ConnectionPool
import structlog

from src.api.config import get_settings

logger = structlog.get_logger(__name__)

# If the initial connection attempt fails (or a later one drops), retry at
# most this often. Without a cooldown, connect() would previously only ever
# run once at process startup — a single blip at boot (or a dropped
# connection later) permanently disabled caching, and everything that
# depends on Redis being reachable (rate limiting, and critically the
# refresh-token rotation concurrency guard) silently fell back to its
# unguarded path for the rest of the worker's life.
_RECONNECT_COOLDOWN_SECONDS = 30


class CacheClient:
    """Async Redis cache client with connection pooling."""

    def __init__(self):
        """Initialize Redis client with connection pool."""
        self.settings = get_settings()
        self.pool: Optional[ConnectionPool] = None
        self.redis: Optional[aioredis.Redis] = None
        self._enabled = False
        self._last_connect_attempt: float = 0.0

    async def connect(self):
        """Establish Redis connection."""
        self._last_connect_attempt = time.time()

        # Check if caching is enabled in config
        if not self.settings.CACHE_ENABLED:
            logger.info("Redis caching disabled in configuration")
            self._enabled = False
            return

        try:
            redis_url = self.settings.REDIS_URL

            self.pool = ConnectionPool.from_url(
                redis_url,
                max_connections=10,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_keepalive=True,
            )

            self.redis = aioredis.Redis(connection_pool=self.pool)

            # Test connection
            await self.redis.ping()
            self._enabled = True
            logger.info("Redis cache connected successfully", url=redis_url.split('@')[0])  # Hide password

        except Exception as e:
            logger.warning(
                "Redis connection failed, caching disabled",
                error=str(e),
                error_type=type(e).__name__,
                target=redis_url.split('@')[-1],  # host:port only, never the credentials segment
            )
            self._enabled = False
            self.redis = None

    async def ensure_connected(self) -> bool:
        """
        Lazily retry a never-established or dropped connection, on a cooldown.

        Call this before any Redis-dependent correctness check (not just
        caching) — e.g. the refresh-token rotation claim guard — so a
        transient outage recovers on its own instead of requiring a process
        restart to notice Redis is back.

        Returns:
            True if Redis is usable after this call, False otherwise.
        """
        if self._enabled and self.redis is not None:
            return True

        if time.time() - self._last_connect_attempt < _RECONNECT_COOLDOWN_SECONDS:
            return False

        await self.connect()
        return self._enabled and self.redis is not None

    async def disconnect(self):
        """Close Redis connection."""
        if self.redis:
            await self.redis.aclose()
            logger.info("Redis cache disconnected")

    async def get(self, key: str) -> Optional[Any]:
        """
        Get value from cache.

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found or cache disabled
        """
        if not await self.ensure_connected():
            return None

        try:
            value = await self.redis.get(key)
            if value is None:
                logger.debug("Cache miss", key=key)
                return None

            logger.debug("Cache hit", key=key)
            return json.loads(value)

        except Exception as e:
            logger.error("Cache get error", key=key, error=str(e))
            return None

    async def set(
        self,
        key: str,
        value: Any,
        ttl: int = 300  # 5 minutes default
    ) -> bool:
        """
        Set value in cache.

        Args:
            key: Cache key
            value: Value to cache (will be JSON serialized)
            ttl: Time to live in seconds

        Returns:
            True if successful, False otherwise
        """
        if not await self.ensure_connected():
            return False

        try:
            serialized = json.dumps(value, default=str)  # default=str handles dates, UUIDs, etc.
            await self.redis.setex(key, ttl, serialized)
            logger.debug("Cache set", key=key, ttl=ttl)
            return True

        except Exception as e:
            logger.error("Cache set error", key=key, error=str(e))
            return False

    async def delete(self, key: str) -> bool:
        """
        Delete key from cache.

        Args:
            key: Cache key to delete

        Returns:
            True if key was deleted, False otherwise
        """
        if not await self.ensure_connected():
            return False

        try:
            result = await self.redis.delete(key)
            logger.debug("Cache delete", key=key, deleted=bool(result))
            return bool(result)

        except Exception as e:
            logger.error("Cache delete error", key=key, error=str(e))
            return False

    async def delete_pattern(self, pattern: str) -> int:
        """
        Delete all keys matching pattern.

        Args:
            pattern: Redis pattern (e.g., "user:123:*")

        Returns:
            Number of keys deleted
        """
        if not await self.ensure_connected():
            return 0

        try:
            deleted = 0
            cursor = 0

            while True:
                cursor, keys = await self.redis.scan(
                    cursor,
                    match=pattern,
                    count=100
                )

                if keys:
                    deleted += await self.redis.delete(*keys)

                if cursor == 0:
                    break

            logger.info("Cache pattern delete", pattern=pattern, deleted=deleted)
            return deleted

        except Exception as e:
            logger.error("Cache pattern delete error", pattern=pattern, error=str(e))
            return 0

    async def clear(self) -> bool:
        """
        Clear all cache (use with caution!).

        Returns:
            True if successful, False otherwise
        """
        if not await self.ensure_connected():
            return False

        try:
            await self.redis.flushdb()
            logger.warning("Cache cleared - all keys deleted")
            return True

        except Exception as e:
            logger.error("Cache clear error", error=str(e))
            return False

    async def get_stats(self) -> dict:
        """
        Get cache statistics.

        Returns:
            Dict with cache stats or empty dict if unavailable
        """
        if not self._enabled or not self.redis:
            return {"enabled": False}

        try:
            info = await self.redis.info("stats")
            return {
                "enabled": True,
                "keyspace_hits": info.get("keyspace_hits", 0),
                "keyspace_misses": info.get("keyspace_misses", 0),
                "hit_rate": self._calculate_hit_rate(
                    info.get("keyspace_hits", 0),
                    info.get("keyspace_misses", 0)
                )
            }

        except Exception as e:
            logger.error("Cache stats error", error=str(e))
            return {"enabled": True, "error": str(e)}

    def _calculate_hit_rate(self, hits: int, misses: int) -> float:
        """Calculate cache hit rate percentage."""
        total = hits + misses
        if total == 0:
            return 0.0
        return round((hits / total) * 100, 2)

    @property
    def is_enabled(self) -> bool:
        """Check if cache is enabled and connected."""
        return self._enabled


# Global cache instance
cache = CacheClient()
