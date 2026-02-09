
"""
Token Cleanup Utility

Provides functions to clean up expired tokens from the blacklist table.
Expired tokens can be safely removed since they would be rejected anyway.

Usage:
    from src.utils.token_cleanup import cleanup_expired_tokens
    from src.api.database.database import SessionLocal

    db = SessionLocal()
    deleted_count = cleanup_expired_tokens(db)
    db.close()
"""

from datetime import datetime
from sqlalchemy import delete
from sqlalchemy.orm import Session
from src.api.models.user_models.token_blacklist import TokenBlacklist
from src.utils.logger import logger


def cleanup_expired_tokens(db: Session) -> int:
    """
    Remove expired tokens from blacklist.

    Tokens that have expired can be safely removed from the blacklist
    since they would be rejected anyway due to expiration. This prevents
    the blacklist table from growing indefinitely and improves query performance.

    Args:
        db: Database session

    Returns:
        Number of tokens deleted

    Raises:
        Exception: If database operation fails (logged and returns 0)

    Example:
        >>> from src.api.database.database import SessionLocal
        >>> db = SessionLocal()
        >>> deleted = cleanup_expired_tokens(db)
        >>> logger.info(f"Deleted {deleted} tokens")
        >>> db.close()
    """
    try:
        # Delete tokens that expired before current time
        cutoff_time = datetime.utcnow()

        result = db.execute(
            delete(TokenBlacklist).where(
                TokenBlacklist.expires_at < cutoff_time
            )
        )
        deleted_count = result.rowcount

        db.commit()

        if deleted_count > 0:
            logger.info(f"Cleaned up {deleted_count} expired tokens from blacklist")
        else:
            logger.debug("No expired tokens to clean up")

        return deleted_count

    except Exception as e:
        logger.error(f"Token cleanup failed: {str(e)}")
        db.rollback()
        return 0
