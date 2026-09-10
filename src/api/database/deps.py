"""
Database dependency functions for FastAPI routes.

This module provides database session dependencies that can be used
with FastAPI's Depends() to inject database sessions into route handlers.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from .async_database import get_async_db


# Alias for backwards compatibility and clearer naming
async def get_db_dependency() -> AsyncSession:
    """
    Database dependency for FastAPI routes.

    This is a wrapper around get_async_db() for backwards compatibility
    and to provide a more explicit name for dependency injection.

    Usage:
        @router.get("/example")
        async def example_route(db: AsyncSession = Depends(get_db_dependency)):
            # Use db session
            result = await db.execute(...)

    Yields:
        AsyncSession: Database session with automatic transaction handling
    """
    async for session in get_async_db():
        yield session


__all__ = ["get_db_dependency", "get_async_db"]
