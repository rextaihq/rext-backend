"""
Caching decorators for async functions.

Provides simple decorators to cache function results with automatic key generation.
"""
from functools import wraps
from typing import Callable, Optional, Any
import hashlib
import inspect
import json
import structlog
from fastapi import Request, BackgroundTasks
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

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
            cached_data = await cache.get(cache_key)
            if cached_data is not None:
                logger.debug(
                    "Cache hit",
                    key=cache_key,
                    function=func.__name__
                )
                
                # Check if we need to reconstruct a JSONResponse
                if isinstance(cached_data, dict) and "__cached_json_response__" in cached_data:
                    return JSONResponse(
                        content=cached_data["content"],
                        status_code=cached_data["status_code"]
                    )
                return cached_data

            # Cache miss - call function
            logger.debug(
                "Cache miss",
                key=cache_key,
                function=func.__name__
            )
            result = await func(*args, **kwargs)

            # Prepare value for caching
            to_cache = result
            if isinstance(result, JSONResponse):
                try:
                    # Cache the decoded content and status code
                    to_cache = {
                        "__cached_json_response__": True,
                        "content": json.loads(result.body.decode()),
                        "status_code": result.status_code
                    }
                except Exception as e:
                    logger.warning("Failed to serialize JSONResponse for cache", error=str(e))
                    return result

            # Cache the result
            settings = get_settings()
            cache_ttl = ttl if ttl is not None else settings.CACHE_DEFAULT_TTL
            await cache.set(cache_key, to_cache, ttl=cache_ttl)

            return result

        return wrapper
    return decorator


def _default_key_builder(prefix: str, func: Callable, args: tuple, kwargs: dict) -> str:
    """
    Default cache key builder.

    Creates a key from function name and hashed arguments.
    Skips system objects like Request, Session, etc.
    """
    # Get function signature to map args to names
    sig = inspect.signature(func)
    bound_args = sig.bind_partial(*args, **kwargs)
    bound_args.apply_defaults()

    # Types to exclude from key generation
    EXCLUDED_TYPES = (Request, AsyncSession, BackgroundTasks)

    # Build key parts, skipping 'self' and system objects
    key_parts = []
    
    for name, value in bound_args.arguments.items():
        if name == 'self':
            continue
            
        # Skip system objects and complex types that shouldn't be in a key
        if isinstance(value, EXCLUDED_TYPES):
            continue

        # Handle SQLAlchemy models - use ID instead of memory address string representation
        if hasattr(value, 'id') and hasattr(value, '__tablename__'):
            key_parts.append(f"{name}={value.id}")
            continue

        # Handle user dicts from get_current_user - only use identity to avoid key change 
        # when other session data changes
        if isinstance(value, dict) and 'identity' in value:
            key_parts.append(f"{name}={value['identity']}")
            continue
            
        key_parts.append(f"{name}={value}")

    # Create hash of all parts
    key_string = "|".join(key_parts)
    key_hash = hashlib.md5(key_string.encode()).hexdigest()[:16]

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
