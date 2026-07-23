"""
Redis client wrapper for caching.

Provides async Redis operations with connection pooling and error handling.
"""
import json
import socket
from urllib.parse import urlparse
from typing import Optional, Any
from redis import asyncio as aioredis
from redis.asyncio import ConnectionPool
import structlog

from src.api.config import get_settings

logger = structlog.get_logger(__name__)


class CacheClient:
    """Async Redis cache client with connection pooling."""

    def __init__(self):
        """Initialize Redis client with connection pool."""
        self.settings = get_settings()
        self.pool: Optional[ConnectionPool] = None
        self.redis: Optional[aioredis.Redis] = None
        self._enabled = False

    async def connect(self):
        """Establish Redis connection."""
        # Check if caching is enabled in config
        if not self.settings.CACHE_ENABLED:
            logger.info("Redis caching disabled in configuration")
            self._enabled = False
            return

        try:
            redis_url = self.settings.REDIS_URL

            self.pool = ConnectionPool.from_url(
                redis_url,
                max_connections=self.settings.REDIS_MAX_CONNECTIONS,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_keepalive=True,
            )

            self.redis = aioredis.Redis(connection_pool=self.pool)

            # Test connection
            await self.redis.ping()
            self._enabled = True
            parsed_url = urlparse(redis_url)
            logger.info(
                "Redis cache connected successfully",
                host=parsed_url.hostname,
                port=parsed_url.port or 6379,
            )

        except Exception as e:
            # Resolve the hostname to its actual IP so a "which Redis did this
            # actually reach" question can be answered from the logs alone —
            # no shell access needed. A DNS alias can point somewhere
            # unexpected (e.g. a different managed resource with the same
            # name on a shared network), and that's invisible without this.
            resolved_ip = None
            try:
                hostname = urlparse(self.settings.REDIS_URL).hostname
                if hostname:
                    resolved_ip = socket.gethostbyname(hostname)
            except Exception:
                resolved_ip = "DNS resolution failed"

            logger.warning(
                "Redis connection failed, caching disabled",
                error=str(e),
                resolved_host=resolved_ip,
            )
            self._enabled = False
            self.redis = None

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
        if not self._enabled or not self.redis:
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
        if not self._enabled or not self.redis:
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
        if not self._enabled or not self.redis:
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
        if not self._enabled or not self.redis:
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
        if not self._enabled or not self.redis:
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
