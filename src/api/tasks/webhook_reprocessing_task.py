"""
Failed-Webhook Reprocessing Background Task

Periodically retries LemonSqueezy webhook events that failed processing, using
the same retry path as the admin endpoint (``WebhookMonitoringService.retry_webhook``).

An event is eligible when it is unprocessed, is still under the retry cap, was
received within the lookback window, and its last attempt is older than the
backoff window. That includes an event with no error: the route stores each
event before acknowledging it, so a process that stopped after the 200 (a
deploy, a crash) leaves it unprocessed, and Lemon Squeezy won't send it again.

Usage:
    python -m src.api.tasks.webhook_reprocessing_task
"""

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from sqlalchemy import and_, select

from src.api.database.async_database import get_async_db_context
from src.api.models.subscription_models.webhooks import WebhookEvent
from src.config.cleanup_config import cleanup_config
from src.services.webhook_monitoring_service import WebhookMonitoringService
from src.utils.logger import logger


async def run_webhook_reprocessing_task() -> Dict[str, Any]:
    """Retry eligible failed webhook events. Returns processing statistics."""
    now = datetime.now(timezone.utc)
    backoff_cutoff = now - timedelta(minutes=cleanup_config.WEBHOOK_REPROCESS_BACKOFF_MINUTES)
    lookback_cutoff = now - timedelta(hours=cleanup_config.WEBHOOK_REPROCESS_LOOKBACK_HOURS)

    stats = {"eligible": 0, "succeeded": 0, "failed": 0, "execution_time": now.isoformat()}

    async with get_async_db_context() as db:
        stmt = (
            select(WebhookEvent.id)
            .where(
                and_(
                    WebhookEvent.processed.is_(False),
                    WebhookEvent.retry_count < cleanup_config.WEBHOOK_REPROCESS_MAX_RETRIES,
                    WebhookEvent.created_at >= lookback_cutoff,
                    WebhookEvent.updated_at <= backoff_cutoff,
                )
            )
            .order_by(WebhookEvent.created_at)
            .limit(cleanup_config.WEBHOOK_REPROCESS_BATCH_LIMIT)
        )
        event_ids = (await db.execute(stmt)).scalars().all()
        stats["eligible"] = len(event_ids)

        if not event_ids:
            logger.info("Webhook reprocessing: no eligible failed events")
            return stats

        logger.info(f"Webhook reprocessing: retrying {len(event_ids)} failed event(s)")
        service = WebhookMonitoringService(db)

        for event_id in event_ids:
            try:
                result = await service.retry_webhook(event_id)
            except Exception as e:  # noqa: BLE001 - one bad event must not stop the batch
                logger.error(
                    f"Webhook reprocessing failed for {event_id}: {e}",
                    extra={"error": str(e)},
                    exc_info=True,
                )
                stats["failed"] += 1
                continue

            if result.get("success"):
                stats["succeeded"] += 1
            else:
                stats["failed"] += 1

    logger.info(
        f"Webhook reprocessing complete: {stats['succeeded']} succeeded, {stats['failed']} failed",
        extra=stats,
    )
    return stats


if __name__ == "__main__":
    result = asyncio.run(run_webhook_reprocessing_task())
    print("\n=== Webhook Reprocessing Results ===")
    print(f"Eligible: {result['eligible']}")
    print(f"Succeeded: {result['succeeded']}")
    print(f"Failed: {result['failed']}")
