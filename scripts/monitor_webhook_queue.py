#!/usr/bin/env python3
"""
Webhook Queue Depth Monitor

Monitors the webhook processing queue and alerts if the queue depth
exceeds thresholds, indicating potential processing delays.

Phase 4, Task 4.2.4

Usage:
    python scripts/monitor_webhook_queue.py

Schedule with cron (every 5 minutes):
    */5 * * * * /path/to/venv/bin/python /path/to/scripts/monitor_webhook_queue.py
"""

import asyncio
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import func, select, and_
from src.api.models.subscription_models.webhooks import WebhookEvent
from src.api.database.async_database import get_async_session
from src.api.lib.sentry_config import trigger_payment_alert
from src.utils.logger import logger


# Thresholds
QUEUE_DEPTH_WARNING = 50
QUEUE_DEPTH_CRITICAL = 100
TIME_WINDOW_HOURS = 1
SLOW_PROCESSING_THRESHOLD_MS = 5000


async def check_webhook_queue():
    """Check webhook queue depth and alert if necessary."""
    try:
        async for session in get_async_session():
            # Count unprocessed webhooks from last hour
            unprocessed_stmt = select(func.count(WebhookEvent.id)).where(
                and_(
                    WebhookEvent.processed == False,
                    WebhookEvent.created_at
                    > datetime.now(timezone.utc) - timedelta(hours=TIME_WINDOW_HOURS),
                )
            )
            unprocessed_result = await session.execute(unprocessed_stmt)
            unprocessed_count = unprocessed_result.scalar() or 0

            # Count total webhooks from last hour
            total_stmt = select(func.count(WebhookEvent.id)).where(
                WebhookEvent.created_at
                > datetime.now(timezone.utc) - timedelta(hours=TIME_WINDOW_HOURS)
            )
            total_result = await session.execute(total_stmt)
            total_count = total_result.scalar() or 0

            # Count failed webhooks
            failed_stmt = select(func.count(WebhookEvent.id)).where(
                and_(
                    WebhookEvent.error_message.isnot(None),
                    WebhookEvent.created_at
                    > datetime.now(timezone.utc) - timedelta(hours=TIME_WINDOW_HOURS),
                )
            )
            failed_result = await session.execute(failed_stmt)
            failed_count = failed_result.scalar() or 0

            # Get oldest unprocessed webhook age
            oldest_unprocessed_stmt = (
                select(WebhookEvent.created_at)
                .where(WebhookEvent.processed == False)
                .order_by(WebhookEvent.created_at.asc())
                .limit(1)
            )
            oldest_result = await session.execute(oldest_unprocessed_stmt)
            oldest_webhook = oldest_result.scalar()

            oldest_age_minutes = 0
            if oldest_webhook:
                oldest_age_minutes = int(
                    (datetime.now(timezone.utc) - oldest_webhook).total_seconds() / 60
                )

            # Log current status
            logger.info(
                "Webhook queue status check",
                extra={
                    "unprocessed_count": unprocessed_count,
                    "total_count": total_count,
                    "failed_count": failed_count,
                    "oldest_age_minutes": oldest_age_minutes,
                    "time_window_hours": TIME_WINDOW_HOURS,
                },
            )

            # Alert if queue depth is critical
            if unprocessed_count >= QUEUE_DEPTH_CRITICAL:
                trigger_payment_alert(
                    alert_type="webhook_queue_critical",
                    message=f"Webhook queue depth CRITICAL: {unprocessed_count} unprocessed events (oldest: {oldest_age_minutes}min old)",
                    severity="critical",
                    context={
                        "queue_depth": unprocessed_count,
                        "total_webhooks": total_count,
                        "failed_count": failed_count,
                        "oldest_age_minutes": oldest_age_minutes,
                        "threshold": QUEUE_DEPTH_CRITICAL,
                    },
                )
                logger.error(
                    f"CRITICAL: Webhook queue depth at {unprocessed_count} events",
                    extra={
                        "queue_depth": unprocessed_count,
                        "oldest_age_minutes": oldest_age_minutes,
                    },
                )
                return False

            # Alert if queue depth is elevated
            elif unprocessed_count >= QUEUE_DEPTH_WARNING:
                trigger_payment_alert(
                    alert_type="webhook_queue_elevated",
                    message=f"Webhook queue depth elevated: {unprocessed_count} unprocessed events (oldest: {oldest_age_minutes}min old)",
                    severity="high",
                    context={
                        "queue_depth": unprocessed_count,
                        "total_webhooks": total_count,
                        "failed_count": failed_count,
                        "oldest_age_minutes": oldest_age_minutes,
                        "threshold": QUEUE_DEPTH_WARNING,
                    },
                )
                logger.warning(
                    f"WARNING: Webhook queue depth at {unprocessed_count} events",
                    extra={
                        "queue_depth": unprocessed_count,
                        "oldest_age_minutes": oldest_age_minutes,
                    },
                )
                return True

            # Alert if oldest webhook is too old (even if queue is small)
            elif oldest_age_minutes > 30 and unprocessed_count > 0:
                trigger_payment_alert(
                    alert_type="webhook_processing_stuck",
                    message=f"Webhook processing appears stuck: {unprocessed_count} events pending, oldest is {oldest_age_minutes} minutes old",
                    severity="high",
                    context={
                        "queue_depth": unprocessed_count,
                        "oldest_age_minutes": oldest_age_minutes,
                    },
                )
                logger.warning(
                    f"WARNING: Oldest webhook is {oldest_age_minutes} minutes old",
                    extra={
                        "queue_depth": unprocessed_count,
                        "oldest_age_minutes": oldest_age_minutes,
                    },
                )
                return True

            # Everything looks good
            logger.info(
                f"Webhook queue healthy: {unprocessed_count} unprocessed, {total_count} total in last {TIME_WINDOW_HOURS}h"
            )
            return True

    except Exception as e:
        logger.error(
            f"Failed to check webhook queue: {str(e)}",
            extra={"error": str(e), "error_type": type(e).__name__},
        )
        # Alert about monitoring failure
        trigger_payment_alert(
            alert_type="webhook_monitor_failure",
            message=f"Webhook queue monitoring script failed: {str(e)}",
            severity="high",
            context={"error": str(e), "error_type": type(e).__name__},
        )
        return False


async def get_queue_statistics():
    """Get detailed queue statistics for reporting."""
    try:
        async for session in get_async_session():
            # Event type breakdown
            event_breakdown_stmt = (
                select(
                    WebhookEvent.event_name,
                    func.count(WebhookEvent.id).label("count"),
                    func.count(WebhookEvent.id)
                    .filter(WebhookEvent.processed == False)
                    .label("pending"),
                    func.count(WebhookEvent.id)
                    .filter(WebhookEvent.error_message.isnot(None))
                    .label("failed"),
                )
                .where(
                    WebhookEvent.created_at
                    > datetime.now(timezone.utc) - timedelta(hours=TIME_WINDOW_HOURS)
                )
                .group_by(WebhookEvent.event_name)
            )
            event_result = await session.execute(event_breakdown_stmt)
            event_stats = event_result.fetchall()

            logger.info(
                "Webhook event type breakdown",
                extra={
                    "stats": [
                        {
                            "event_name": row.event_name,
                            "total": row.count,
                            "pending": row.pending,
                            "failed": row.failed,
                        }
                        for row in event_stats
                    ]
                },
            )

            return event_stats

    except Exception as e:
        logger.error(f"Failed to get queue statistics: {str(e)}", extra={"error": str(e)})
        return []


async def main():
    """Main entry point."""
    logger.info("Starting webhook queue monitoring check")

    # Check queue depth
    queue_healthy = await check_webhook_queue()

    # Get detailed statistics
    await get_queue_statistics()

    if queue_healthy:
        logger.info("Webhook queue monitoring check completed successfully")
        sys.exit(0)
    else:
        logger.error("Webhook queue monitoring check detected issues")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
