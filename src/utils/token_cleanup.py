"""
Token Cleanup Utility

Provides functions to clean up expired tokens from the blacklist table.
Expired tokens can be safely removed since they would be rejected anyway.

Usage:
    from src.utils.token_cleanup import cleanup_expired_tokens
    from src.api.database.async_database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        deleted_count = await cleanup_expired_tokens(db)
"""

from datetime import datetime, timezone

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.models.user_models.token_blacklist import TokenBlacklist
from src.utils.logger import logger


async def cleanup_expired_tokens(db: AsyncSession) -> int:
    """
    Remove expired tokens from blacklist.

    Tokens that have expired can be safely removed from the blacklist
    since they would be rejected anyway due to expiration. This prevents
    the blacklist table from growing indefinitely and improves query performance.

    Args:
        db: Async database session

    Returns:
        Number of tokens deleted

    Raises:
        Exception: If database operation fails (logged and returns 0)
    """
    try:
        cutoff_time = datetime.now(timezone.utc)

        stmt = delete(TokenBlacklist).where(TokenBlacklist.expires_at < cutoff_time)
        result = await db.execute(stmt)
        await db.commit()

        deleted_count = result.rowcount

        if deleted_count > 0:
            logger.info(f"Cleaned up {deleted_count} expired tokens from blacklist")
        else:
            logger.debug("No expired tokens to clean up")

        return deleted_count

    except Exception as e:
        logger.error(f"Token cleanup failed: {str(e)}")
        await db.rollback()
        return 0
