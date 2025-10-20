"""
Caching decorators for async functions.

Provides simple decorators to cache function results with automatic key generation.
"""
from functools import wraps
from typing import Callable, Optional
import hashlib
import inspect
import structlog

from src.api.cache.redis_client import cache
from src.api.config import get_settings

logger = structlog.get_logger(__name__)


def cached(
    key_prefix: str,
    ttl: Optional[int] = None,
    key_builder: Optional[Callable] = None
):
    """
    Cache decorator for async functions.

    Args:
        key_prefix: Prefix for cache keys (e.g., "user:permissions")
        ttl: Time to live in seconds (defaults to CACHE_DEFAULT_TTL from config)
        key_builder: Optional custom function to build cache key from args/kwargs
                     Signature: key_builder(*args, **kwargs) -> str

    Example:
        ```python
        @cached(key_prefix="user:profile", ttl=300)
        async def get_user(self, user_id: str):
            return await self.db.execute(select(User).where(User.id == user_id))

        # With custom key builder:
        @cached(
            key_prefix="permissions",
            ttl=600,
            key_builder=lambda self, user_id, workspace_id=None:
                f"{user_id}:{workspace_id or 'global'}"
        )
        async def get_permissions(self, user_id: str, workspace_id: Optional[str] = None):
            ...
        ```
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Skip caching if cache is not enabled
            if not cache.is_enabled:
                return await func(*args, **kwargs)

            # Build cache key
            if key_builder:
                try:
                    key_suffix = key_builder(*args, **kwargs)
                    cache_key = f"{key_prefix}:{key_suffix}"
                except Exception as e:
                    logger.warning(
                        "Custom key_builder failed, using default",
                        error=str(e),
                        function=func.__name__
                    )
                    cache_key = _default_key_builder(key_prefix, func, args, kwargs)
            else:
                cache_key = _default_key_builder(key_prefix, func, args, kwargs)

            # Try to get from cache
            cached_value = await cache.get(cache_key)
            if cached_value is not None:
                logger.debug(
                    "Cache hit",
                    key=cache_key,
                    function=func.__name__
                )
                return cached_value

            # Cache miss - call function
            logger.debug(
                "Cache miss",
                key=cache_key,
                function=func.__name__
            )
            result = await func(*args, **kwargs)

            # Cache the result
            settings = get_settings()
            cache_ttl = ttl if ttl is not None else settings.CACHE_DEFAULT_TTL
            await cache.set(cache_key, result, ttl=cache_ttl)

            return result

        return wrapper
    return decorator


def _default_key_builder(prefix: str, func: Callable, args: tuple, kwargs: dict) -> str:
    """
    Default cache key builder.

    Creates a key from function name and hashed arguments.
    Skips 'self' argument for methods.
    """
    # Get function signature to identify 'self'
    sig = inspect.signature(func)
    params = list(sig.parameters.keys())

    # Build key parts, skipping 'self'
    key_parts = []

    # Process positional args (skip first if it's 'self')
    start_idx = 1 if params and params[0] == 'self' else 0
    for i, arg in enumerate(args[start_idx:], start=start_idx):
        key_parts.append(str(arg))

    # Process keyword args
    for k, v in sorted(kwargs.items()):
        key_parts.append(f"{k}={v}")

    # Create hash of all parts
    key_string = "|".join(key_parts)
    key_hash = hashlib.md5(key_string.encode()).hexdigest()[:16]  # Short hash

    return f"{prefix}:{func.__name__}:{key_hash}"


async def invalidate_cache(pattern: str) -> int:
    """
    Invalidate cache entries matching a pattern.

    Args:
        pattern: Redis pattern (e.g., "user:123:*" or "permissions:*")

    Returns:
        Number of keys deleted

    Example:
        ```python
        # After updating user permissions
        await invalidate_cache(f"user:permissions:{user_id}:*")

        # After updating all subscription plans
        await invalidate_cache("subscription:plans:*")
        ```
    """
    if not cache.is_enabled:
        return 0

    deleted = await cache.delete_pattern(pattern)
    logger.info("Cache invalidated", pattern=pattern, deleted=deleted)
    return deleted


async def invalidate_cache_key(key: str) -> bool:
    """
    Invalidate a specific cache key.

    Args:
        key: Exact cache key to delete

    Returns:
        True if key was deleted, False otherwise
    """
    if not cache.is_enabled:
        return False

    deleted = await cache.delete(key)
    if deleted:
        logger.info("Cache key invalidated", key=key)
    return deleted
