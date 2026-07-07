"""
Scheduled Tasks

Background scheduled tasks using APScheduler.
Handles data cleanup, billing automation, trial management, and other periodic operations.

Environment variables:
- SCHEDULER_ENABLED: Master switch for all scheduled tasks (default: true)
- CLEANUP_ENABLED: Toggle data cleanup task (default: true)
- BILLING_TASKS_ENABLED: Toggle subscription maintenance tasks (default: true)
- TRIAL_TASKS_ENABLED: Toggle trial expiration tasks (default: true)
- DUNNING_TASKS_ENABLED: Toggle payment dunning reminders (default: true)
- GRACE_PERIOD_TASKS_ENABLED: Toggle grace period expiration (default: true)
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
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.api.tasks.trial_expiration_task import run_trial_expiration_task
from src.api.tasks.payment_dunning_task import run_payment_dunning_task
from src.api.tasks.grace_period_expiration_task import run_grace_period_expiration_task
from src.api.tasks.subscription_tasks import run_daily_subscription_tasks
from src.api.models.content_models.content import Content
from src.api.models.content_models.publishing_result import ContentPublishingResult, PublishingStatus
from src.api.models.integrations.workspace_integration import WorkspaceIntegration
from src.api.schema.content_schema import ContentCreate, ContentSEODataSchema
from src.web.wordpress import WordPressPublisher
from src.utils.logger import logger
from src.tasks.google_sync_task import run_google_daily_sync_task
from src.api.config import settings

_PUBLISH_CONCURRENCY = 5
_PUBLISH_BATCH_LIMIT = 200


async def run_scheduled_publish_task() -> None:
    logger.info("[ScheduledPublish] Task fired.")
    async with AsyncSessionLocal() as db:
        now = datetime.now(timezone.utc)

        stmt = (
            select(ContentPublishingResult)
            .where(
                ContentPublishingResult.status == PublishingStatus.SCHEDULED,
                ContentPublishingResult.scheduled_publish_at <= now,
                ContentPublishingResult.wp_post_id.is_(None),
            )
            .order_by(ContentPublishingResult.scheduled_publish_at)
            .limit(_PUBLISH_BATCH_LIMIT)
        )
        due: list[ContentPublishingResult] = list((await db.execute(stmt)).scalars().all())

        if not due:
            logger.info("[ScheduledPublish] Nothing due.")
            return

        logger.info(f"[ScheduledPublish] {len(due)} record(s) due for publish.")

        content_ids = list({r.content_id for r in due})
        site_ids    = list({r.site_id    for r in due})

        contents_map: dict = {
            c.id: c for c in (
                await db.execute(
                    select(Content)
                    .options(selectinload(Content.seo_data))
                    .where(Content.id.in_(content_ids))
                )
            ).scalars().all()
        }
        integrations_map: dict = {
            i.id: i for i in (
                await db.execute(
                    select(WorkspaceIntegration).where(WorkspaceIntegration.id.in_(site_ids))
                )
            ).scalars().all()
        }

        sem = asyncio.Semaphore(_PUBLISH_CONCURRENCY)

        async def _publish_one(rec: ContentPublishingResult) -> None:
            content     = contents_map.get(rec.content_id)
            integration = integrations_map.get(rec.site_id)

            if not content or not integration or not integration.is_active:
                logger.warning(
                    f"[ScheduledPublish] Skipping {rec.id} — "
                    f"content={'missing' if not content else 'ok'} "
                    f"integration={'missing/inactive' if not integration or not integration.is_active else 'ok'}"
                )
                return

            seo = getattr(content, "seo_data", None)
            seo_schema = None
            if seo:
                seo_schema = ContentSEODataSchema(
                    meta_title=seo.meta_title,
                    meta_description=seo.meta_description,
                    focus_keyphrase=seo.focus_keyphrase,
                    trust_score=seo.trust_score,
                )

            content_data = ContentCreate(
                title=content.title,
                introduction=content.introduction,
                body_markdown=content.body_markdown,
                body_html=content.body_html,
                tags=content.tags,
                seo_data=seo_schema,
                workspace_id=None,
                content_type=None,
            )

            async with sem:
                try:
                    async with WordPressPublisher(
                        site_url=integration.site_url,
                        api_endpoint=integration.api_endpoint,
                        username=integration.username,
                        app_password=integration.app_password,
                        api_key=integration.api_key,
                    ) as wp:
                        wp_response = await wp.publish_post(data=content_data, status="publish")

                    rec.wp_post_id           = wp_response.get("post_id")
                    rec.external_url         = wp_response.get("link")
                    rec.status               = PublishingStatus.PUBLISHED
                    rec.scheduled_publish_at = None
                    rec.last_synced_at       = datetime.now(timezone.utc)
                    rec.sync_error           = None

                    content.wordpress_post_id      = rec.wp_post_id
                    content.wordpress_url          = rec.external_url
                    content.wordpress_published_at = datetime.now(timezone.utc)
                    content.status                 = "published"

                    logger.info(
                        f"[ScheduledPublish] Published content={content.id} "
                        f"wp_post_id={rec.wp_post_id} url={rec.external_url}"
                    )
                except Exception as e:
                    logger.error(f"[ScheduledPublish] Failed {rec.id}: {e}")
                    rec.sync_error = str(e)

        await asyncio.gather(*[_publish_one(r) for r in due])
        await db.commit()
        logger.info("[ScheduledPublish] Cycle complete.")


class ScheduledTaskManager:
    """Manager for scheduled background tasks."""

    def __init__(self):
        """Initialize task manager."""
        self.scheduler: Optional[AsyncIOScheduler] = None
        self._running = False

    def start(self):
        """Start the scheduler and register tasks."""
        if not cleanup_config.SCHEDULER_ENABLED:
            logger.info("Scheduler disabled (SCHEDULER_ENABLED=false). No scheduled tasks will run.")
            return

        if not APSCHEDULER_AVAILABLE:
            logger.error(
                "CRITICAL: APScheduler not installed — ALL billing automation is disabled! "
                "Trial expiration, payment dunning, grace period enforcement, usage resets, "
                "and data cleanup will NOT run. Install with: pip install 'apscheduler>=3.10.0,<4.0.0'"
            )
            return

        if self.scheduler and self._running:
            logger.warning("Scheduler already running")
            return

        logger.info("Starting scheduled task manager...")

        self.scheduler = AsyncIOScheduler()

        # Schedule daily cleanup at configured time (default 2 AM)
        if cleanup_config.CLEANUP_ENABLED:
            self.scheduler.add_job(
                self._run_data_cleanup,
                trigger=CronTrigger(
                    hour=cleanup_config.CLEANUP_HOUR,
                    minute=cleanup_config.CLEANUP_MINUTE
                ),
                id="data_cleanup",
                name="Daily data cleanup",
                replace_existing=True,
                max_instances=1,
            )
            logger.info("Registered task: data_cleanup")
        else:
            logger.info("Data cleanup task disabled (CLEANUP_ENABLED=false)")

        # Trial expiration check — daily at midnight
        if cleanup_config.TRIAL_TASKS_ENABLED:
            self.scheduler.add_job(
                run_trial_expiration_task,
                trigger=CronTrigger(hour=0, minute=0),
                id="trial_expiration",
                name="Daily trial expiration check",
                replace_existing=True,
                max_instances=1,
            )
            logger.info("Registered task: trial_expiration")
        else:
            logger.info("Trial expiration task disabled (TRIAL_TASKS_ENABLED=false)")

        # Payment dunning reminders — daily at 1 AM
        if cleanup_config.DUNNING_TASKS_ENABLED:
            self.scheduler.add_job(
                run_payment_dunning_task,
                trigger=CronTrigger(hour=1, minute=0),
                id="payment_dunning",
                name="Daily payment dunning",
                replace_existing=True,
                max_instances=1,
            )
            logger.info("Registered task: payment_dunning")
        else:
            logger.info("Payment dunning task disabled (DUNNING_TASKS_ENABLED=false)")

        # Grace period expiration — daily at 1:30 AM
        if cleanup_config.GRACE_PERIOD_TASKS_ENABLED:
            self.scheduler.add_job(
                run_grace_period_expiration_task,
                trigger=CronTrigger(hour=1, minute=30),
                id="grace_period_expiration",
                name="Daily grace period expiration",
                replace_existing=True,
                max_instances=1,
            )
            logger.info("Registered task: grace_period_expiration")
        else:
            logger.info("Grace period expiration task disabled (GRACE_PERIOD_TASKS_ENABLED=false)")

        # Scheduled content publish — every 5 minutes
        self.scheduler.add_job(
            run_scheduled_publish_task,
            trigger="interval",
            minutes=1,
            id="scheduled_content_publish",
            name="Scheduled content publish",
            replace_existing=True,
            max_instances=1,
        )
        logger.info("Registered task: scheduled_content_publish")

        # Subscription maintenance — daily at 3 AM
        if cleanup_config.BILLING_TASKS_ENABLED:
            self.scheduler.add_job(
                run_daily_subscription_tasks,
                trigger=CronTrigger(hour=3, minute=0),
                id="subscription_maintenance",
                name="Daily subscription maintenance",
                replace_existing=True,
                max_instances=1,
            )
            logger.info("Registered task: subscription_maintenance")
        else:
            logger.info("Subscription maintenance task disabled (BILLING_TASKS_ENABLED=false)")

        # Google Analytics Incremental Sync — daily at 4 AM
        if getattr(settings, "GOOGLE_SYNC_ENABLED", False):
            self.scheduler.add_job(
                run_google_daily_sync_task,
                trigger=CronTrigger(hour=4, minute=0),
                id="google_daily_sync",
                name="Daily Google Analytics Sync",
                replace_existing=True,
                max_instances=1,
            )
            logger.info("Registered task: google_daily_sync")
        else:
            logger.info("Google Analytics Sync task disabled (GOOGLE_SYNC_ENABLED=false)")

        # Only start the scheduler if at least one job was registered
        if self.scheduler.get_jobs():
            self.scheduler.start()
            self._running = True
            logger.info(
                f"Scheduled tasks started with {len(self.scheduler.get_jobs())} job(s).",
                extra={
                    "cleanup_hour": cleanup_config.CLEANUP_HOUR,
                    "cleanup_minute": cleanup_config.CLEANUP_MINUTE,
                    "jobs": [job.id for job in self.scheduler.get_jobs()]
                }
            )
        else:
            logger.warning("No scheduled tasks registered. Scheduler not started.")

    def shutdown(self):
        """Shutdown the scheduler gracefully."""
        if self.scheduler and self._running:
            logger.info("Shutting down scheduled task manager...")
            self.scheduler.shutdown(wait=True)
            self._running = False
            logger.info("Scheduled task manager shut down")

    def get_status(self) -> dict:
        """Get scheduler status for health checks."""
        if not self._running or not self.scheduler:
            return {
                "running": False,
                "jobs": [],
                "reason": "Scheduler not started" if not APSCHEDULER_AVAILABLE else "SCHEDULER_ENABLED is False"
            }

        jobs = []
        for job in self.scheduler.get_jobs():
            jobs.append({
                "id": job.id,
                "name": job.name,
                "next_run": job.next_run_time.isoformat() if job.next_run_time else None
            })

        return {
            "running": True,
            "job_count": len(jobs),
            "jobs": jobs
        }

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
