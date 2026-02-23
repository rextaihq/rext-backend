"""
Payment Dunning Background Task

This task should be scheduled to run daily (recommended at midnight UTC).
It sends escalating payment reminder emails to users with failed payments.

Dunning Schedule:
- Day 1 after failure: First reminder (informative)
- Day 3 after failure: Second reminder (urgent)
- Day 6 after failure: Final warning (very urgent - 1 day before suspension)

Usage:
    # Run manually for testing
    python -m src.api.tasks.payment_dunning_task

    # Or schedule with cron
    0 0 * * * cd /path/to/app && python -m src.api.tasks.payment_dunning_task
"""

import asyncio
from datetime import datetime, timezone
from typing import Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.database.async_database import get_async_db_context
from src.services.dunning_service import DunningService
from src.utils.logger import logger


class PaymentDunningTask:
    """Background task for payment dunning (reminder emails)."""

    def __init__(self, db: AsyncSession):
        """
        Initialize task with database session.

        Args:
            db: Async database session
        """
        self.db = db
        self.dunning_service = DunningService(db)

    async def run(self) -> Dict[str, Any]:
        """
        Run the payment dunning task.

        Processes all three dunning stages (1-day, 3-day, 6-day reminders).

        Returns:
            Dict with processing statistics
        """
        logger.info("=== Payment Dunning Task Started ===")
        logger.info(f"Execution time: {datetime.now(timezone.utc).isoformat()}")

        try:
            stats = {
                "execution_time": datetime.now(timezone.utc).isoformat(),
                "day_1": {},
                "day_3": {},
                "day_6": {},
                "total_sent": 0,
                "total_failed": 0
            }

            # Process 1-day dunning (first reminder)
            logger.info("--- Processing 1-day dunning reminders ---")
            day_1_stats = await self.dunning_service.process_dunning_reminders(
                days_since_failure=1
            )
            stats["day_1"] = day_1_stats
            stats["total_sent"] += day_1_stats["sent"]
            stats["total_failed"] += day_1_stats["failed"]

            # Process 3-day dunning (second reminder)
            logger.info("--- Processing 3-day dunning reminders ---")
            day_3_stats = await self.dunning_service.process_dunning_reminders(
                days_since_failure=3
            )
            stats["day_3"] = day_3_stats
            stats["total_sent"] += day_3_stats["sent"]
            stats["total_failed"] += day_3_stats["failed"]

            # Process 6-day dunning (final warning)
            logger.info("--- Processing 6-day dunning reminders ---")
            day_6_stats = await self.dunning_service.process_dunning_reminders(
                days_since_failure=6
            )
            stats["day_6"] = day_6_stats
            stats["total_sent"] += day_6_stats["sent"]
            stats["total_failed"] += day_6_stats["failed"]

            # Commit all changes
            await self.db.commit()

            logger.info("=== Payment Dunning Task Completed Successfully ===")
            logger.info(f"Total emails sent: {stats['total_sent']}")
            logger.info(f"Total failures: {stats['total_failed']}")
            logger.info(f"Day 1 reminders: {day_1_stats['sent']}/{day_1_stats['total_subscriptions']}")
            logger.info(f"Day 3 reminders: {day_3_stats['sent']}/{day_3_stats['total_subscriptions']}")
            logger.info(f"Day 6 reminders: {day_6_stats['sent']}/{day_6_stats['total_subscriptions']}")

            return stats

        except Exception as e:
            logger.error(
                f"Payment dunning task failed: {str(e)}",
                extra={"error": str(e)},
                exc_info=True
            )
            # Rollback on error
            await self.db.rollback()
            raise


async def run_payment_dunning_task() -> Dict[str, Any]:
    """
    Entry point for running the payment dunning task.

    This can be called by a cron job or scheduler.

    Returns:
        Dict with processing statistics
    """
    async with get_async_db_context() as db:
        task = PaymentDunningTask(db)
        return await task.run()


if __name__ == "__main__":
    """
    Run this script directly for testing or manual execution:

    python -m src.api.tasks.payment_dunning_task
    """
    result = asyncio.run(run_payment_dunning_task())
    print("\n=== Dunning Task Results ===")
    print(f"Total emails sent: {result['total_sent']}")
    print(f"Total failures: {result['total_failed']}")
    print(f"\nDay 1 reminders: {result['day_1']['sent']}/{result['day_1']['total_subscriptions']}")
    print(f"Day 3 reminders: {result['day_3']['sent']}/{result['day_3']['total_subscriptions']}")
    print(f"Day 6 reminders: {result['day_6']['sent']}/{result['day_6']['total_subscriptions']}")
