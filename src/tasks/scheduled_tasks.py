"""
Scheduled Tasks

Background scheduled tasks using APScheduler.
Handles data cleanup, billing automation, trial management, and other periodic operations.

Environment variables:
- SCHEDULER_ENABLED: Master switch for all scheduled tasks (default: true)
- CLEANUP_ENABLED: Toggle data cleanup task (default: true)
- BILLING_TASKS_ENABLED: Toggle subscription maintenance tasks (default: true)
- TRIAL_TASKS_ENABLED: Toggle trial expiration tasks (default: true)
- DIGEST_TASKS_ENABLED: Toggle the email digest (default: true)
- WEBHOOK_REPROCESS_TASKS_ENABLED: Toggle retrying failed LemonSqueezy webhooks (default: true)

Local checkouts set SCHEDULER_ENABLED=false (see .env.example), so a development
instance never runs billing, trial or publishing jobs against its database.
"""

import asyncio
from typing import Optional

import httpx

try:
    from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_MISSED
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.cron import CronTrigger

    APSCHEDULER_AVAILABLE = True
except ImportError:
    APSCHEDULER_AVAILABLE = False
    AsyncIOScheduler = None
    CronTrigger = None
    EVENT_JOB_ERROR = EVENT_JOB_MISSED = None

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from src.api.config import get_settings
from src.api.database.async_database import AsyncSessionLocal
from src.api.middleware.exceptions import (
    ExternalServiceTimeoutException,
    RextExternalServiceException,
)
from src.api.models.content_models.content import Content
from src.api.models.content_models.publishing_result import (
    ContentPublishingResult,
    PublishingStatus,
)
from src.api.models.integrations.workspace_integration import WorkspaceIntegration
from src.api.models.knowledge_models.persona_model import Persona
from src.api.models.user_models.users import Users
from src.api.models.workspace_models.workspace_model import WorkspaceModel
from src.api.schema.content_schema import ContentCreate, ContentSEODataSchema
from src.api.schema.response_schemas import ErrorSeverity

# TODO: src.api.tasks.webhook_reprocessing_task missing — disabled until committed
# from src.api.tasks.webhook_reprocessing_task import run_webhook_reprocessing_task
from src.api.tasks.api_usage_rollup_task import run_api_usage_rollup_task
from src.api.tasks.subscription_reconcile_task import run_subscription_reconcile_task
from src.api.tasks.subscription_tasks import run_daily_subscription_tasks
from src.api.tasks.trial_expiration_task import run_trial_expiration_task
from src.api.tasks.webhook_reprocessing_task import run_webhook_reprocessing_task
from src.config.cleanup_config import cleanup_config
from src.services.data_cleanup_service import DataCleanupService
from src.services.digest_service import run_digest_task
from src.services.email_helpers import send_content_publish_failed_email
from src.services.notification_helper import notify_now
from src.services.notifications_services import notification_service
from src.utils.logger import logger
from src.web.wordpress import (
    BodyImageUploadError,
    SiteRefusedCredentialsError,
    WordPressPublisher,
)

_PUBLISH_CONCURRENCY = 5
_PUBLISH_BATCH_LIMIT = 200


def _is_transient_publish_error(exc: Exception) -> bool:
    """Whether a retry has a realistic chance of succeeding.

    Only network/timeout/5xx-type failures are worth retrying — bad
    credentials, missing content, 4xx validation errors, etc. will fail
    the exact same way on every attempt, so retrying them just burns the
    retry budget and delays the FAILED notification for no benefit.
    """
    if isinstance(exc, SiteRefusedCredentialsError):
        # The site refused the connection's key (HTTP 401 or 403), and refuses it again.
        return False
    if isinstance(exc, BodyImageUploadError):
        # A refused image (HTTP 413, not an image) is refused again, and each attempt
        # would leave the images uploaded before it in the media library again.
        return exc.transient
    if isinstance(exc, (ExternalServiceTimeoutException, RextExternalServiceException)):
        return True
    if isinstance(exc, (httpx.TimeoutException, httpx.ConnectError, httpx.NetworkError)):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        return status == 429 or status >= 500
    return False


def _get_publish_failure_reason(exc: Exception) -> str:
    """Plain-language reason for a publish failure, for the user-facing
    email/notification. Falls back to a generic message for anything not
    explicitly recognized, so every failure type still gets a sensible
    explanation.
    """
    if isinstance(exc, (BodyImageUploadError, SiteRefusedCredentialsError)):
        return exc.notice
    if isinstance(exc, (ExternalServiceTimeoutException, httpx.TimeoutException)):
        return "Your WordPress site took too long to respond (timed out)."
    if isinstance(exc, (httpx.ConnectError, httpx.NetworkError)):
        return "Your WordPress site could not be reached. It may be down or unreachable."
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        if status in (401, 403):
            return "Your WordPress credentials are invalid or have expired."
        if status == 404:
            return "The WordPress site or publishing endpoint could not be found."
        if status == 429:
            return (
                "Your WordPress site is rate-limiting requests. "
                "Too many publish attempts in a short time."
            )
        if status >= 500:
            return "Your WordPress site returned a server error."
        return f"Your WordPress site rejected the request ({status})."
    if isinstance(exc, RextExternalServiceException):
        return "There was a problem communicating with your WordPress site."
    return "Publishing failed due to an unexpected error."


async def run_scheduled_publish_task() -> None:
    """Scheduled publish with connection-safe phased execution.

    Phase 1 — Load:    short-lived DB session, extract data into plain dicts.
    Phase 2 — Publish: WordPress HTTP calls, NO DB session held.
    Phase 3 — Persist: fresh DB session to write results and commit.
    Phase 4 — Notify:  failure notifications with their own DB sessions.
    """
    logger.info("[ScheduledPublish] Task fired.")

    # ── Phase 1: Load data (short-lived DB session) ────────────────────
    publish_items: list[dict] = []

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
        site_ids = list({r.site_id for r in due})

        contents_map: dict = {
            c.id: c
            for c in (
                await db.execute(
                    select(Content)
                    .options(selectinload(Content.seo_data))
                    .where(Content.id.in_(content_ids))
                )
            )
            .scalars()
            .all()
        }
        integrations_map: dict = {
            i.id: i
            for i in (
                await db.execute(
                    select(WorkspaceIntegration).where(WorkspaceIntegration.id.in_(site_ids))
                )
            )
            .scalars()
            .all()
        }

        workspace_ids = list({c.workspace_id for c in contents_map.values()})
        workspaces_map: dict = {
            w.id: w
            for w in (
                await db.execute(select(WorkspaceModel).where(WorkspaceModel.id.in_(workspace_ids)))
            )
            .scalars()
            .all()
        }
        owner_ids = list({c.created_by_user_id for c in contents_map.values()})
        users_map: dict = {
            u.id: u
            for u in (await db.execute(select(Users).where(Users.id.in_(owner_ids))))
            .scalars()
            .all()
        }

        # Author personas chosen in the outline step — a scheduled publish must
        # credit the same author an immediate publish would.
        persona_ids = [c.persona_id for c in contents_map.values() if c.persona_id]
        personas_map: dict = (
            {
                p.id: p
                for p in (await db.execute(select(Persona).where(Persona.id.in_(persona_ids))))
                .scalars()
                .all()
            }
            if persona_ids
            else {}
        )

        # Extract all data into plain dicts so we can close the session.
        # ORM objects become detached once the session closes, so every
        # value needed later must be copied here.
        for rec in due:
            content = contents_map.get(rec.content_id)
            integration = integrations_map.get(rec.site_id)

            integration_ok = bool(integration and integration.is_active)
            if not content or not integration_ok:
                logger.warning(
                    f"[ScheduledPublish] Skipping {rec.id} — "
                    f"content={'missing' if not content else 'ok'} "
                    f"integration={'ok' if integration_ok else 'missing/inactive'}"
                )
                continue

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
                category=content.category,
                seo_data=seo_schema,
                workspace_id=None,
                content_type=None,
                images_data=content.images_data,
            )

            owner = users_map.get(content.created_by_user_id)
            workspace = workspaces_map.get(content.workspace_id)
            persona = personas_map.get(content.persona_id) if content.persona_id else None

            publish_items.append(
                {
                    "rec_id": rec.id,
                    "content_id": content.id,
                    "retry_count": rec.retry_count or 0,
                    "content_data": content_data,
                    "author_name": (persona.full_name or persona.name) if persona else None,
                    "author_email": persona.email if persona else None,
                    "integration_config": {
                        "site_url": integration.site_url,
                        "api_endpoint": integration.api_endpoint,
                        "username": integration.username,
                        "app_password": integration.app_password,
                        "api_key": integration.api_key,
                    },
                    # Plain-value context for failure notifications (no ORM refs)
                    "notification_ctx": {
                        "content_title": content.title,
                        "content_id": str(content.id),
                        "workspace_id": content.workspace_id,
                        "integration_site_url": integration.site_url,
                        "owner_id": owner.id if owner else None,
                        "owner_email": owner.email if owner else None,
                        "owner_name": (owner.display_name or owner.full_name or owner.email)
                        if owner
                        else None,
                        "workspace_slug": workspace.slug if workspace else None,
                    },
                }
            )
    # ── DB session closed ──────────────────────────────────────────────

    if not publish_items:
        logger.info("[ScheduledPublish] No publishable items after filtering.")
        return

    # ── Phase 2: Publish via HTTP (NO DB session held) ─────────────────
    sem = asyncio.Semaphore(_PUBLISH_CONCURRENCY)
    # Each entry: (item_dict, "success"|"error", wp_response_dict | Exception)
    publish_results: list[tuple] = []

    async def _publish_one_http(item: dict) -> None:
        intg = item["integration_config"]
        async with sem:
            try:
                async with WordPressPublisher(
                    site_url=intg["site_url"],
                    api_endpoint=intg["api_endpoint"],
                    username=intg["username"],
                    app_password=intg["app_password"],
                    api_key=intg["api_key"],
                ) as wp:
                    wp_response = await wp.publish_post(
                        data=item["content_data"],
                        status="publish",
                        author_name=item.get("author_name"),
                        author_email=item.get("author_email"),
                    )
                publish_results.append((item, "success", wp_response))
                logger.info(
                    f"[ScheduledPublish] Published content={item['content_id']} "
                    f"wp_post_id={wp_response.get('post_id')} url={wp_response.get('link')}"
                )
            except Exception as e:
                logger.error(f"[ScheduledPublish] Failed {item['rec_id']}: {e}")
                publish_results.append((item, "error", e))

    await asyncio.gather(*[_publish_one_http(item) for item in publish_items])

    # ── Phase 3: Persist results (fresh short-lived DB session) ────────
    pending_notifications: list[dict] = []
    published_notifications: list[dict] = []

    async with AsyncSessionLocal() as db:
        for item, status, response in publish_results:
            rec = await db.get(ContentPublishingResult, item["rec_id"])
            content = await db.get(Content, item["content_id"])

            if not rec:
                logger.warning(
                    f"[ScheduledPublish] Record {item['rec_id']} disappeared — skipping."
                )
                continue

            if status == "success":
                rec.wp_post_id = response.get("post_id")
                rec.external_url = response.get("link")
                rec.status = PublishingStatus.PUBLISHED
                rec.scheduled_publish_at = None
                rec.last_synced_at = datetime.now(timezone.utc)
                rec.sync_error = None
                rec.retry_count = 0

                if content:
                    content.wordpress_post_id = rec.wp_post_id
                    content.wordpress_url = rec.external_url
                    content.wordpress_published_at = datetime.now(timezone.utc)
                    content.status = "published"
                    published_notifications.append(
                        {**item["notification_ctx"], "url": rec.external_url}
                    )
            else:
                error = response  # Exception instance
                new_retry_count = item["retry_count"] + 1
                rec.retry_count = new_retry_count
                rec.sync_error = str(error)

                max_retries = cleanup_config.SCHEDULED_PUBLISH_MAX_RETRIES
                will_retry = _is_transient_publish_error(error) and new_retry_count < max_retries
                next_retry_at = None

                if will_retry:
                    next_retry_at = datetime.now(timezone.utc) + timedelta(
                        minutes=cleanup_config.SCHEDULED_PUBLISH_RETRY_INTERVAL_MINUTES
                    )
                    rec.scheduled_publish_at = next_retry_at
                else:
                    rec.status = PublishingStatus.FAILED
                    rec.scheduled_publish_at = None
                    if content:
                        content.status = "failed"
                        content.updated_at = datetime.now(timezone.utc)

                # Only notify once scheduling is truly done — after the final
                # attempt fails, not on intermediate retries.
                ctx = item["notification_ctx"]
                if not will_retry and ctx.get("owner_id") and ctx.get("owner_email"):
                    pending_notifications.append(
                        {
                            **ctx,
                            "error_message": _get_publish_failure_reason(error),
                            "attempt_number": new_retry_count,
                            "max_retries": max_retries,
                        }
                    )

        await db.commit()
    # ── DB session closed ──────────────────────────────────────────────

    # ── Phase 4: Send notifications (own sessions, after commit)
    for ctx in published_notifications:
        if ctx.get("owner_id"):
            await notify_now(
                user_id=ctx["owner_id"],
                pref_flag="gen_published",
                message=f'"{ctx["content_title"]}" was published successfully.',
                payload={"content_id": ctx["content_id"], "url": ctx["url"]},
                workspace_id=ctx.get("workspace_id"),
            )

    for notif in pending_notifications:
        try:
            await _send_publish_failure_notification(notif)
        except Exception as notify_err:
            logger.error(
                f"[ScheduledPublish] Failed to notify for content "
                f"{notif.get('content_id')}: {notify_err}"
            )

    logger.info("[ScheduledPublish] Cycle complete.")


async def _send_publish_failure_notification(notif: dict) -> None:
    """Send email + in-app notification once scheduling is done retrying.

    Only called for the final failure (all attempts exhausted, or a
    permanent error that skipped retries entirely) — never on an
    intermediate retry — so the user gets exactly one notification per
    failed post, with a plain-language reason instead of a raw error.

    Uses its own isolated DB session so the caller does not need to hold
    a connection open during the external email API call.
    """
    frontend_url = get_settings().FRONTEND_URL.rstrip("/")
    workspace_path = f"/w/{notif['workspace_slug']}" if notif.get("workspace_slug") else ""
    content_url = f"{frontend_url}{workspace_path}/content/{notif['content_id']}"

    message = (
        f'We couldn\'t publish "{notif["content_title"]}" after '
        f"{notif['attempt_number']} attempt(s): {notif['error_message']}"
    )

    async with AsyncSessionLocal() as db:
        try:
            await send_content_publish_failed_email(
                db=db,
                recipient_email=notif["owner_email"],
                user_id=notif["owner_id"],
                user_name=notif["owner_name"],
                content_title=notif["content_title"],
                site_url=notif.get("integration_site_url") or "your site",
                error_message=notif["error_message"],
                will_retry=False,
                attempt_number=notif["attempt_number"],
                max_retries=notif["max_retries"],
                retry_url=content_url,
                reschedule_url=content_url,
                next_retry_at=None,
                workspace_id=notif.get("workspace_id"),
            )
        except Exception as email_err:
            logger.error(
                f"[ScheduledPublish] Email notification failed for content "
                f"{notif['content_id']}: {email_err}"
            )

        try:
            await notification_service.send_error_notification(
                user_id=notif["owner_id"],
                message=message,
                payload={
                    "content_id": notif["content_id"],
                    "attempt_number": notif["attempt_number"],
                    "max_retries": notif["max_retries"],
                    "reason": notif["error_message"],
                },
                db=db,
                title="Scheduled Publish Failed",
                category="publish_failed",
                workspace_id=notif.get("workspace_id"),
            )
        except Exception as notif_err:
            logger.error(
                f"[ScheduledPublish] In-app notification failed for content "
                f"{notif['content_id']}: {notif_err}"
            )

        await db.commit()


class ScheduledTaskManager:
    """Manager for scheduled background tasks."""

    def __init__(self):
        """Initialize task manager."""
        self.scheduler: Optional[AsyncIOScheduler] = None
        self._running = False

    def _register_failure_listener(self):
        """
        Record scheduled-job failures in the admin Error Logs.

        Background jobs never pass through the HTTP stack, so no exception
        handler ever sees them. A crashed billing or cleanup job wrote a line
        to the application log and was otherwise invisible to operators --
        exactly the failures that most need surfacing, since nobody is watching
        a request when they happen.
        """
        loop = asyncio.get_event_loop()

        def _on_job_failure(event):
            job = self.scheduler.get_job(event.job_id) if self.scheduler else None
            job_name = getattr(job, "name", None) or event.job_id
            missed = EVENT_JOB_MISSED is not None and event.code == EVENT_JOB_MISSED

            if missed:
                message = f"Scheduled job missed its run window: {job_name}"
                severity, stack_trace = ErrorSeverity.HIGH.value, None
            else:
                message = f"Scheduled job failed: {job_name}: {event.exception}"
                # APScheduler formats the traceback for us; it is the only
                # record of where a background job died.
                severity = ErrorSeverity.CRITICAL.value
                stack_trace = getattr(event, "traceback", None)

            logger.error(message)

            async def _persist():
                try:
                    from src.services.monitoring_service import MonitoringService

                    await MonitoringService.persist_error_log(
                        api_severity=severity,
                        message=message,
                        source=f"scheduler {event.job_id}",
                        path=f"/scheduler/{event.job_id}",
                        stack_trace=stack_trace,
                        metadata={
                            "job_id": event.job_id,
                            "job_name": job_name,
                            "exception_type": type(event.exception).__name__
                            if getattr(event, "exception", None)
                            else None,
                            "scheduled_run_time": str(getattr(event, "scheduled_run_time", ""))
                            or None,
                        },
                    )
                except Exception as persist_error:  # noqa: BLE001 - never propagate
                    logger.warning(f"Failed to persist scheduled job error: {persist_error}")

            # Listeners may be invoked from a worker thread, so hand the
            # coroutine back to the scheduler's loop rather than assuming one
            # is running here.
            try:
                asyncio.run_coroutine_threadsafe(_persist(), loop)
            except Exception as dispatch_error:  # noqa: BLE001 - never propagate
                logger.warning(f"Failed to dispatch scheduled job error log: {dispatch_error}")

        mask = EVENT_JOB_ERROR
        if EVENT_JOB_MISSED is not None:
            mask |= EVENT_JOB_MISSED
        self.scheduler.add_listener(_on_job_failure, mask)

    def start(self):
        """Start the scheduler and register tasks."""
        if not cleanup_config.SCHEDULER_ENABLED:
            logger.info("Scheduler disabled (SCHEDULER_ENABLED=false).")
            return

        if not APSCHEDULER_AVAILABLE:
            logger.warning(
                "CRITICAL: APScheduler not installed — ALL billing automation is disabled! "
                "Trial expiration, usage resets, "
                "and data cleanup will NOT run."
            )
            return

        if self.scheduler and self._running:
            logger.warning("Scheduler already running")
            return

        logger.info("Starting scheduled task manager...")

        self.scheduler = AsyncIOScheduler()
        self._register_failure_listener()

        # Schedule daily cleanup at configured time (default 2 AM)
        if cleanup_config.CLEANUP_ENABLED:
            self.scheduler.add_job(
                self._run_data_cleanup,
                trigger=CronTrigger(
                    hour=cleanup_config.CLEANUP_HOUR, minute=cleanup_config.CLEANUP_MINUTE
                ),
                id="data_cleanup",
                name="Daily data cleanup",
                replace_existing=True,
                max_instances=1,
            )
            logger.info("Registered task: data_cleanup")
        else:
            logger.info("Data cleanup task disabled (CLEANUP_ENABLED=false)")

        # Subscription reconcile with Lemon Squeezy — daily at 2:30 AM. It is subscription
        # maintenance, so BILLING_TASKS_ENABLED=false turns it off too.
        if cleanup_config.BILLING_TASKS_ENABLED and cleanup_config.SUBSCRIPTION_RECONCILE_ENABLED:
            self.scheduler.add_job(
                run_subscription_reconcile_task,
                trigger=CronTrigger(hour=2, minute=30),
                id="subscription_reconcile",
                name="Nightly subscription reconcile with Lemon Squeezy",
                replace_existing=True,
                max_instances=1,
            )
            logger.info("Registered task: subscription_reconcile")
        else:
            logger.info(
                "Subscription reconcile task disabled "
                "(BILLING_TASKS_ENABLED or SUBSCRIPTION_RECONCILE_ENABLED is false)"
            )

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

        # Scheduled content publish — every minute, so a post goes out within a
        # minute of its scheduled time
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

        # Copy live API counters into api_usage_hourly. Must run well inside
        # the Redis metric TTL so no minute bucket expires undrained.
        self.scheduler.add_job(
            run_api_usage_rollup_task,
            trigger="interval",
            minutes=cleanup_config.API_USAGE_ROLLUP_INTERVAL_MINUTES,
            id="api_usage_rollup",
            name="API usage rollup",
            replace_existing=True,
            max_instances=1,
        )
        logger.info("Registered task: api_usage_rollup")

        # Failed-webhook automatic reprocessing — every N minutes
        if cleanup_config.WEBHOOK_REPROCESS_TASKS_ENABLED:
            self.scheduler.add_job(
                run_webhook_reprocessing_task,
                trigger="interval",
                minutes=cleanup_config.WEBHOOK_REPROCESS_INTERVAL_MINUTES,
                id="webhook_reprocessing",
                name="Failed webhook reprocessing",
                replace_existing=True,
                max_instances=1,
            )
            logger.info("Registered task: webhook_reprocessing")
        else:
            logger.info(
                "Webhook reprocessing task disabled (WEBHOOK_REPROCESS_TASKS_ENABLED=false)"
            )

        # Email digest — checked daily; each user gets one per their cadence
        if cleanup_config.DIGEST_TASKS_ENABLED:
            self.scheduler.add_job(
                run_digest_task,
                trigger=CronTrigger(
                    hour=cleanup_config.DIGEST_HOUR,
                    minute=cleanup_config.DIGEST_MINUTE,
                ),
                id="email_digest",
                name="Email activity digest",
                replace_existing=True,
                max_instances=1,
            )
            logger.info("Registered task: email_digest")
        else:
            logger.info("Email digest task disabled (DIGEST_TASKS_ENABLED=false)")

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

        # Only start the scheduler if at least one job was registered
        if self.scheduler.get_jobs():
            self.scheduler.start()
            self._running = True
            logger.info(
                f"Scheduled tasks started with {len(self.scheduler.get_jobs())} job(s).",
                extra={
                    "cleanup_hour": cleanup_config.CLEANUP_HOUR,
                    "cleanup_minute": cleanup_config.CLEANUP_MINUTE,
                    "jobs": [job.id for job in self.scheduler.get_jobs()],
                },
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
            reason_msg = (
                "Scheduler not started"
                if not APSCHEDULER_AVAILABLE
                else "SCHEDULER_ENABLED is False"
            )
            return {
                "running": False,
                "jobs": [],
                "reason": reason_msg,
            }

        jobs = []
        for job in self.scheduler.get_jobs():
            jobs.append(
                {
                    "id": job.id,
                    "name": job.name,
                    "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
                }
            )

        return {"running": True, "job_count": len(jobs), "jobs": jobs}

    async def _run_data_cleanup(self):
        """Run data cleanup task."""
        logger.info("Starting scheduled data cleanup task...")

        try:
            async with AsyncSessionLocal() as db:
                cleanup_service = DataCleanupService(db=db, dry_run=cleanup_config.CLEANUP_DRY_RUN)
                results = await cleanup_service.cleanup_all()

                logger.info(
                    "Scheduled data cleanup completed successfully", extra={"results": results}
                )

        except Exception as e:
            logger.error(
                f"Scheduled data cleanup failed: {str(e)}", exc_info=True, extra={"error": str(e)}
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
            extra={"results": results},
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
