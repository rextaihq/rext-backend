"""
Scheduled Tasks

Background scheduled tasks using APScheduler.
Handles data cleanup, maintenance, and other periodic operations.

To enable scheduled tasks, set CLEANUP_ENABLED=true in environment variables.
"""

import asyncio
from typing import Optional

try:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.cron import CronTrigger
    APSCHEDULER_AVAILABLE = True
except ImportError:
    APSCHEDULER_AVAILABLE = False
    AsyncIOScheduler = None
    CronTrigger = None

from src.api.database.async_database import AsyncSessionLocal
from src.services.data_cleanup_service import DataCleanupService
from src.config.cleanup_config import cleanup_config
from src.utils.logger import logger


class ScheduledTaskManager:
    """Manager for scheduled background tasks."""

    def __init__(self):
        """Initialize task manager."""
        self.scheduler: Optional[AsyncIOScheduler] = None
        self._running = False

    def start(self):
        """Start the scheduler and register tasks."""
        if not cleanup_config.CLEANUP_ENABLED:
            logger.info("Scheduled tasks disabled (CLEANUP_ENABLED=false)")
            return

        if not APSCHEDULER_AVAILABLE:
            logger.warning(
                "APScheduler not installed. Scheduled tasks disabled. "
                "Install with: pip install apscheduler"
            )
            return

        if self.scheduler and self._running:
            logger.warning("Scheduler already running")
            return

        logger.info("Starting scheduled task manager...")

        self.scheduler = AsyncIOScheduler()

        # Schedule daily cleanup at configured time (default 2 AM)
        self.scheduler.add_job(
            self._run_data_cleanup,
            trigger=CronTrigger(
                hour=cleanup_config.CLEANUP_HOUR,
                minute=cleanup_config.CLEANUP_MINUTE
            ),
            id="data_cleanup",
            name="Daily data cleanup",
            replace_existing=True,
            max_instances=1,  # Prevent overlapping executions
        )

        self.scheduler.start()
        self._running = True

        logger.info(
            f"Scheduled tasks started. Data cleanup will run daily at {cleanup_config.CLEANUP_HOUR:02d}:{cleanup_config.CLEANUP_MINUTE:02d}",
            extra={
                "cleanup_hour": cleanup_config.CLEANUP_HOUR,
                "cleanup_minute": cleanup_config.CLEANUP_MINUTE,
                "retention_periods": cleanup_config.get_retention_summary()
            }
        )

    def shutdown(self):
        """Shutdown the scheduler gracefully."""
        if self.scheduler and self._running:
            logger.info("Shutting down scheduled task manager...")
            self.scheduler.shutdown(wait=True)
            self._running = False
            logger.info("Scheduled task manager shut down")

    async def _run_data_cleanup(self):
        """Run data cleanup task."""
        logger.info("Starting scheduled data cleanup task...")

        try:
            async with AsyncSessionLocal() as db:
                cleanup_service = DataCleanupService(
                    db=db,
                    dry_run=cleanup_config.CLEANUP_DRY_RUN
                )
                results = await cleanup_service.cleanup_all()

                logger.info(
                    f"Scheduled data cleanup completed successfully",
                    extra={"results": results}
                )

        except Exception as e:
            logger.error(
                f"Scheduled data cleanup failed: {str(e)}",
                exc_info=True,
                extra={"error": str(e)}
            )
            raise

    async def run_cleanup_now(self, dry_run: bool = False):
        """
        Manually trigger data cleanup (useful for testing or manual runs).

        Args:
            dry_run: If True, only count records without deleting

        Returns:
            Cleanup results dictionary
        """
        logger.info(f"{'[DRY RUN] ' if dry_run else ''}Running manual data cleanup...")

        async with AsyncSessionLocal() as db:
            cleanup_service = DataCleanupService(db=db, dry_run=dry_run)
            results = await cleanup_service.cleanup_all()

        logger.info(
            f"{'[DRY RUN] ' if dry_run else ''}Manual data cleanup completed",
            extra={"results": results}
        )

        return results


# Global singleton instance
task_manager = ScheduledTaskManager()


def start_scheduled_tasks():
    """Start scheduled tasks (called from main.py on startup)."""
    task_manager.start()


def shutdown_scheduled_tasks():
    """Shutdown scheduled tasks (called from main.py on shutdown)."""
    task_manager.shutdown()


async def run_cleanup_manually(dry_run: bool = False):
    """
    Run cleanup manually (useful for testing or scripts).

    Args:
        dry_run: If True, only count records without deleting

    Returns:
        Cleanup results dictionary
    """
    return await task_manager.run_cleanup_now(dry_run=dry_run)
