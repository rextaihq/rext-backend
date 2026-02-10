"""
Grace Period Expiration Background Task

This task should be scheduled to run daily (recommended at midnight UTC).
It automatically suspends subscriptions whose grace period has expired.

Grace Period Flow:
1. Payment fails → SUSPENDED status with 7-day grace period
2. Dunning emails sent (days 1, 3, 6)
3. Day 7 → Grace period expires → This task runs
4. Subscription → EXPIRED status, access removed, email sent

Usage:
    # Run manually for testing
    python -m src.api.tasks.grace_period_expiration_task

    # Or schedule with cron
    0 0 * * * cd /path/to/app && python -m src.api.tasks.grace_period_expiration_task
"""

import asyncio
from datetime import datetime
from typing import Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.database.async_database import get_async_db_context
from src.services.grace_period_service import GracePeriodService
from src.utils.logger import logger


class GracePeriodExpirationTask:
    """Background task for grace period expiration and suspension."""

    def __init__(self, db: AsyncSession):
        """
        Initialize task with database session.

        Args:
            db: Async database session
        """
        self.db = db
        self.grace_period_service = GracePeriodService(db)

    async def run(self) -> Dict[str, Any]:
        """
        Run the grace period expiration task.

        Suspends all subscriptions with expired grace periods.

        Returns:
            Dict with processing statistics
        """
        logger.info("=== Grace Period Expiration Task Started ===")
        logger.info(f"Execution time: {datetime.now(timezone.utc).isoformat()}")

        try:
            # Process all grace period expirations
            stats = await self.grace_period_service.process_grace_period_expirations()

            # Add execution time
            stats["execution_time"] = datetime.now(timezone.utc).isoformat()

            # Commit all changes
            await self.db.commit()

            logger.info("=== Grace Period Expiration Task Completed Successfully ===")
            logger.info(f"Subscriptions suspended: {stats['suspended']}")
            logger.info(f"Failed: {stats['failed']}")
            logger.info(f"Total processed: {stats['total_subscriptions']}")

            return stats

        except Exception as e:
            logger.error(
                f"Grace period expiration task failed: {str(e)}",
                extra={"error": str(e)},
                exc_info=True
            )
            # Rollback on error
            await self.db.rollback()
            raise


async def run_grace_period_expiration_task() -> Dict[str, Any]:
    """
    Entry point for running the grace period expiration task.

    This can be called by a cron job or scheduler.

    Returns:
        Dict with processing statistics
    """
    async with get_async_db_context() as db:
        task = GracePeriodExpirationTask(db)
        return await task.run()


if __name__ == "__main__":
    """
    Run this script directly for testing or manual execution:

    python -m src.api.tasks.grace_period_expiration_task
    """
    result = asyncio.run(run_grace_period_expiration_task())
    print("\n=== Grace Period Expiration Results ===")
    print(f"Total subscriptions processed: {result['total_subscriptions']}")
    print(f"Successfully suspended: {result['suspended']}")
    print(f"Failed: {result['failed']}")
