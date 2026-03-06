#!/usr/bin/env python3
"""
Script to clean up expired tokens from blacklist.

This script removes expired tokens from the token_blacklist table to prevent
unbounded growth and maintain query performance.

Usage:
    Manual run:
        python3 scripts/cleanup_tokens.py

    Cron job (runs every 6 hours):
        0 */6 * * * cd /path/to/rext-backend && python3 scripts/cleanup_tokens.py >> logs/token_cleanup.log 2>&1

    Daily at 2 AM:
        0 2 * * * cd /path/to/rext-backend && python3 scripts/cleanup_tokens.py >> logs/token_cleanup.log 2>&1
"""


import asyncio
import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from src.api.database.async_database import AsyncSessionLocal
from src.utils.token_cleanup import cleanup_expired_tokens
from src.utils.logger import logger


async def main():
    """Main cleanup function."""
    logger.info("Starting token cleanup job")

    try:
        async with AsyncSessionLocal() as db:
            deleted_count = await cleanup_expired_tokens(db)
            logger.info(f"Token cleanup completed. Deleted {deleted_count} tokens.")

            if deleted_count > 0:
                print(f"Cleaned up {deleted_count} expired tokens")
            else:
                print("No expired tokens to clean up")

            return 0
    except Exception as e:
        logger.error(f"Token cleanup job failed: {str(e)}")
        print(f"Token cleanup failed: {str(e)}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))