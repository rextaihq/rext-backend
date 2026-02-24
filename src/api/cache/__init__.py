"""Cache package public interface for API-layer caching utilities."""

from .decorators import cached, invalidate_cache, invalidate_cache_key
from .redis_client import cache

__all__ = [
    "cache",
    "cached",
    "invalidate_cache",
    "invalidate_cache_key",
]
