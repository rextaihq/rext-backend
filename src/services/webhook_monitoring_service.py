"""
Webhook Monitoring Service

Provides webhook event tracking and monitoring capabilities:
- List recent webhook events
- Get failed webhook events
- Retry failed webhooks
- Get webhook statistics
"""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
from uuid import UUID

from sqlalchemy import and_, case, desc, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from src.api.database.async_database import AsyncSessionLocal
from src.api.models.subscription_models.webhooks import WebhookEvent
from src.services.lemonsqueezy_webhook_service import LemonSqueezyWebhookService
from src.services.webhook_handlers import register_default_handlers
from src.utils.logger import logger


def _mask_email(email: str) -> str:
    """
    Mask an email address for display in monitoring contexts.

    Examples:
        "john.doe@example.com" -> "jo***@example.com"
        "a@b.com" -> "a***@b.com"
        None or invalid -> "***"
    """
    if not email or not isinstance(email, str) or "@" not in email:
        return "***"
    local, domain = email.rsplit("@", 1)
    if len(local) <= 1:
        return f"{local[0]}***@{domain}"
    return f"{local[:2]}***@{domain}"


class WebhookMonitoringService:
    """Service for monitoring and managing webhook events."""

    _SENSITIVE_KEYS = {
        "name",
        "address",
        "phone",
        "api_key",
        "token",
        "secret",
        "authorization",
        "card_number",
        "card_last_four",
        "payment_method",
        "iban",
        "metadata",
        "custom_data",
    }

    def __init__(self, db: AsyncSession):
        """Initialize service with database session."""
        self.db = db
        self.webhook_service = LemonSqueezyWebhookService(db)

    def _mask_email(self, value: Optional[str]) -> Optional[str]:
        """Partially mask email address for PII protection."""
        if not value or "@" not in value:
            return value
        try:
            local, domain = value.split("@", 1)
            if len(local) <= 2:
                return "***@" + domain
            return local[:2] + "***@" + domain
        except ValueError:
            return value

    def _redact_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Recursively redact sensitive keys from payload."""

        def _walk(value: Any, parent_key: Optional[str] = None) -> Any:
            if isinstance(value, dict):
                out: Dict[str, Any] = {}
                for k, v in value.items():
                    key_lower = k.lower()
                    if key_lower in self._SENSITIVE_KEYS:
                        out[k] = "[REDACTED]"
                    else:
                        out[k] = _walk(v, k)
                return out
            if isinstance(value, list):
                return [_walk(item, parent_key) for item in value]
            if (
                isinstance(value, str)
                and parent_key
                and parent_key.lower() in ["user_email", "customer_email", "email"]
            ):
                return self._mask_email(value)
            return value

        return _walk(deepcopy(payload))

    async def get_webhook_events(
        self,
        limit: int = 50,
        offset: int = 0,
        event_name: Optional[str] = None,
        processed: Optional[bool] = None,
        hours: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Get webhook events with optional filters.

        Args:
            limit: Maximum number of events to return (default 50, max 100)
            offset: Offset for pagination (default 0)
            event_name: Filter by event name (e.g., "subscription_created")
            processed: Filter by processed status (True/False/None for all)
            hours: Only show events from last N hours (optional)

        Returns:
            Dictionary with webhook events and metadata:
            {
                "events": [...],
                "total": int,
                "limit": int,
                "offset": int,
                "filters": {...}
            }
        """
        try:
            # Build query conditions
            conditions = []

            if event_name:
                conditions.append(WebhookEvent.event_name == event_name)

            if processed is not None:
                conditions.append(WebhookEvent.processed == processed)

            if hours:
                cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours)
                conditions.append(WebhookEvent.created_at >= cutoff_time)

            # Count total matching eventss
            count_stmt = select(func.count(WebhookEvent.id))
            if conditions:
                count_stmt = count_stmt.where(and_(*conditions))

            count_result = await self.db.execute(count_stmt)
            total_count = count_result.scalar() or 0

            # Get events
            stmt = select(WebhookEvent).order_by(desc(WebhookEvent.created_at))

            if conditions:
                stmt = stmt.where(and_(*conditions))

            # Apply pagination
            stmt = stmt.limit(min(limit, 100)).offset(offset)

            result = await self.db.execute(stmt)
            events = result.scalars().all()

            # Serialize events
            events_data = []
            for event in events:
                events_data.append(
                    {
                        "id": str(event.id),
                        "event_id": event.event_id,
                        "event_name": event.event_name,
                        "processed": event.processed,
                        "processed_at": event.processed_at.isoformat()
                        if event.processed_at
                        else None,
                        "error_message": event.error_message,
                        "retry_count": event.retry_count,
                        "created_at": event.created_at.isoformat() if event.created_at else None,
                        "updated_at": event.updated_at.isoformat() if event.updated_at else None,
                        # Include subset of payload for monitoring
                        "payload_summary": self._summarize_payload(event.payload)
                        if event.payload
                        else None,
                    }
                )

            logger.info(
                f"Retrieved {len(events)} webhook events",
                extra={
                    "total": total_count,
                    "limit": limit,
                    "offset": offset,
                    "event_name": event_name,
                    "processed": processed,
                },
            )

            return {
                "events": events_data,
                "total": total_count,
                "limit": limit,
                "offset": offset,
                "filters": {"event_name": event_name, "processed": processed, "hours": hours},
            }

        except Exception as e:
            logger.error(f"Failed to get webhook events: {str(e)}", extra={"error": str(e)})
            raise

    async def get_failed_webhooks(
        self,
        limit: int = 50,
        offset: int = 0,
        hours: Optional[int] = 24,
        include_payload: bool = False,
    ) -> Dict[str, Any]:
        """
        Get failed webhook events.

        Args:
            limit: Maximum number of events to return (default 50)
            offset: Offset for pagination (default 0)
            hours: Only show events from last N hours (default 24)
            include_payload: Whether to include redacted payload body

        Returns:
            Dictionary with failed webhook events:
            {
                "events": [...],
                "total": int,
                "limit": int,
                "offset": int
            }
        """
        try:
            # Build conditions for failed webhooks
            conditions = [WebhookEvent.processed.is_(False), WebhookEvent.error_message.isnot(None)]

            if hours:
                cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours)
                conditions.append(WebhookEvent.created_at >= cutoff_time)

            # Count total failed events
            count_stmt = select(func.count(WebhookEvent.id)).where(and_(*conditions))
            count_result = await self.db.execute(count_stmt)
            total_count = count_result.scalar() or 0

            # Get failed events
            stmt = (
                select(WebhookEvent)
                .where(and_(*conditions))
                .order_by(desc(WebhookEvent.created_at))
                .limit(limit)
                .offset(offset)
            )

            result = await self.db.execute(stmt)
            events = result.scalars().all()

            # Serialize events with more details for troubleshooting
            events_data = []
            for event in events:
                event_payload = event.payload or {}
                events_data.append(
                    {
                        "id": str(event.id),
                        "event_id": event.event_id,
                        "event_name": event.event_name,
                        "error_message": event.error_message,
                        "retry_count": event.retry_count,
                        "created_at": event.created_at.isoformat() if event.created_at else None,
                        "updated_at": event.updated_at.isoformat() if event.updated_at else None,
                        "payload_summary": self._summarize_payload(event_payload),
                        "payload": self._redact_payload(event_payload) if include_payload else None,
                    }
                )

            logger.info(
                f"Retrieved {len(events)} failed webhook events",
                extra={"total": total_count, "limit": limit, "offset": offset},
            )

            return {"events": events_data, "total": total_count, "limit": limit, "offset": offset}

        except Exception as e:
            logger.error(f"Failed to get failed webhooks: {str(e)}", extra={"error": str(e)})
            raise

    async def retry_webhook(self, webhook_id: UUID) -> Dict[str, Any]:
        """
        Retry processing a failed webhook event.

        The webhook event is located by its database id (``webhook_events.id``).
        The original stored payload is re-routed through the full handler
        registry (the same handlers used by the live webhook receiver) inside a
        dedicated transaction. The resulting status (processed / failed) is
        persisted in its own transaction so it survives a handler rollback.

        Args:
            webhook_id: Database id of the webhook event to retry

        Returns:
            {"success": bool, "message": str, "event": {...} | None}
        """
        # Locate the event (read-only on the request session).
        stmt = select(WebhookEvent).where(WebhookEvent.id == webhook_id)
        result = await self.db.execute(stmt)
        event = result.scalar_one_or_none()

        if not event:
            logger.warning(f"Webhook event not found: {webhook_id}")
            return {"success": False, "message": "Webhook event not found", "event": None}

        if event.processed and not event.error_message:
            logger.info(f"Webhook already processed: {webhook_id}")
            return {
                "success": False,
                "message": "Webhook event already processed successfully - no retry needed",
                "event": self._serialize_event(event),
            }

        event_db_id = event.id
        event_name = event.event_name
        lemonsqueezy_event_id = event.event_id

        logger.info(
            f"Retrying webhook event: {webhook_id} "
            f"(event_name={event_name}, lemonsqueezy_event_id={lemonsqueezy_event_id})"
        )

        now = datetime.now(timezone.utc)

        # Reprocess the stored payload in a dedicated transaction with the full
        # handler registry so a partial failure cannot corrupt the request tx.
        processing_db = AsyncSessionLocal()
        try:
            webhook_service = LemonSqueezyWebhookService(processing_db)
            register_default_handlers(webhook_service)

            reprocess_target = await processing_db.get(WebhookEvent, event_db_id)
            await webhook_service.reprocess_event(webhook_event=reprocess_target)
            await processing_db.commit()
            success_result = True
            error_message: Optional[str] = None
        except Exception as process_error:  # noqa: BLE001 - result surfaced to admin
            await processing_db.rollback()
            success_result = False
            error_message = str(process_error)
            logger.error(
                f"Failed to retry webhook {webhook_id}: {error_message}",
                extra={"error": error_message},
                exc_info=True,
            )
        finally:
            await processing_db.close()

        # Persist the retry outcome in its own transaction.
        async with AsyncSessionLocal() as status_db:
            row = await status_db.get(WebhookEvent, event_db_id)
            if row is not None:
                row.retry_count = (row.retry_count or 0) + 1
                row.updated_at = now
                if success_result:
                    row.processed = True
                    row.processed_at = now
                    row.error_message = None
                else:
                    row.processed = False
                    row.error_message = error_message
                await status_db.commit()
                serialized = self._serialize_event(row)
            else:
                serialized = self._serialize_event(event)

        if success_result:
            logger.info(f"Successfully retried webhook: {webhook_id}")
            return {
                "success": True,
                "message": "Webhook reprocessed successfully",
                "event": serialized,
            }
        return {
            "success": False,
            "message": f"Retry failed: {error_message}",
            "event": serialized,
        }

    async def get_webhook_statistics(self, hours: Optional[int] = 24) -> Dict[str, Any]:
        """
        Get webhook processing statistics.

        Args:
            hours: Statistics for last N hours (default 24, None for all time)

        Returns:
            Dictionary with webhook statistics:
            {
                "total_events": int,
                "processed": int,
                "failed": int,
                "pending": int,
                "success_rate": float,
                "by_event_type": [...],
                "recent_errors": [...]
            }
        """
        try:
            # Build time filter
            time_condition = []
            if hours:
                cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours)
                time_condition.append(WebhookEvent.created_at >= cutoff_time)

            # Total events
            stmt_total = select(func.count(WebhookEvent.id))
            if time_condition:
                stmt_total = stmt_total.where(and_(*time_condition))

            result_total = await self.db.execute(stmt_total)
            total_events = result_total.scalar() or 0

            # Processed successfully
            stmt_processed = select(func.count(WebhookEvent.id)).where(
                WebhookEvent.processed.is_(True),
                WebhookEvent.error_message.is_(None),
                *time_condition,
            )
            result_processed = await self.db.execute(stmt_processed)
            processed_count = result_processed.scalar() or 0

            # Failed (have error message)
            stmt_failed = select(func.count(WebhookEvent.id)).where(
                WebhookEvent.error_message.isnot(None), *time_condition
            )
            result_failed = await self.db.execute(stmt_failed)
            failed_count = result_failed.scalar() or 0

            # Pending (not processed, no error)
            stmt_pending = select(func.count(WebhookEvent.id)).where(
                WebhookEvent.processed.is_(False),
                WebhookEvent.error_message.is_(None),
                *time_condition,
            )
            result_pending = await self.db.execute(stmt_pending)
            pending_count = result_pending.scalar() or 0

            # Calculate success rate
            if total_events > 0:
                success_rate = (processed_count / total_events) * 100
            else:
                success_rate = 0.0

            # Get stats by event type
            stmt_by_type = select(
                WebhookEvent.event_name,
                func.count(WebhookEvent.id).label("count"),
                func.sum(case((WebhookEvent.processed, 1), else_=0)).label("processed"),
                func.sum(case((WebhookEvent.error_message.isnot(None), 1), else_=0)).label(
                    "failed"
                ),
            ).group_by(WebhookEvent.event_name)

            if time_condition:
                stmt_by_type = stmt_by_type.where(and_(*time_condition))

            result_by_type = await self.db.execute(stmt_by_type)
            rows_by_type = result_by_type.all()

            by_event_type = []
            for row in rows_by_type:
                by_event_type.append(
                    {
                        "event_name": row.event_name,
                        "total": row.count,
                        "processed": row.processed or 0,
                        "failed": row.failed or 0,
                    }
                )

            # Get recent errors (last 10)
            stmt_errors = (
                select(WebhookEvent.event_name, WebhookEvent.error_message, WebhookEvent.created_at)
                .where(WebhookEvent.error_message.isnot(None), *time_condition)
                .order_by(desc(WebhookEvent.created_at))
                .limit(10)
            )

            result_errors = await self.db.execute(stmt_errors)
            rows_errors = result_errors.all()

            recent_errors = []
            for row in rows_errors:
                recent_errors.append(
                    {
                        "event_name": row.event_name,
                        "error_message": row.error_message,
                        "created_at": row.created_at.isoformat() if row.created_at else None,
                    }
                )

            logger.info(
                f"Webhook statistics: {total_events} total, {processed_count} processed, {failed_count} failed",
                extra={
                    "total": total_events,
                    "processed": processed_count,
                    "failed": failed_count,
                    "success_rate": success_rate,
                },
            )

            return {
                "total_events": total_events,
                "processed": processed_count,
                "failed": failed_count,
                "pending": pending_count,
                "success_rate": round(success_rate, 2),
                "period_hours": hours,
                "by_event_type": by_event_type,
                "recent_errors": recent_errors,
            }

        except Exception as e:
            logger.error(f"Failed to get webhook statistics: {str(e)}", extra={"error": str(e)})
            raise

    def _summarize_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a summary of the webhook payload for monitoring.
        PII fields are masked to comply with data minimization principles
        (GDPR Article 5(1)(c), CCPA).

        Args:
            payload: Full webhook payload

        Returns:
            Summarized payload with key information (PII masked)
        """
        summary = {}

        # Common LemonSqueezy webhook structure
        if "data" in payload:
            data = payload["data"]
            summary["id"] = data.get("id")
            summary["type"] = data.get("type")

            # Extract key attributes with PII masking
            if "attributes" in data:
                attrs = data["attributes"]
                summary["status"] = attrs.get("status")
                summary["user_email_masked"] = _mask_email(attrs.get("user_email"))
                summary["has_customer_id"] = bool(attrs.get("customer_id"))

        # Include meta information
        if "meta" in payload:
            summary["meta"] = payload["meta"]

        return summary

    def _redact_payload_pii(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a deep copy of the payload with PII fields redacted.
        Used when the full payload structure is needed for debugging
        but PII must not be exposed.

        Args:
            payload: Original webhook payload

        Returns:
            Payload copy with PII fields masked
        """
        import copy

        redacted = copy.deepcopy(payload)

        if "data" in redacted and "attributes" in redacted["data"]:
            attrs = redacted["data"]["attributes"]
            if "user_email" in attrs:
                attrs["user_email"] = _mask_email(attrs["user_email"])
            if "customer_id" in attrs:
                attrs["customer_id"] = "[REDACTED]"

        return redacted

    def _serialize_event(self, event: WebhookEvent) -> Dict[str, Any]:
        """Serialize a webhook event to dictionary."""
        if event.processed and not event.error_message:
            status = "processed"
        elif event.error_message:
            status = "failed"
        else:
            status = "pending"
        return {
            "id": str(event.id),
            "event_id": event.event_id,
            "event_name": event.event_name,
            "processed": event.processed,
            "processed_at": event.processed_at.isoformat() if event.processed_at else None,
            "error_message": event.error_message,
            "retry_count": event.retry_count,
            "status": status,
            "created_at": event.created_at.isoformat() if event.created_at else None,
            "updated_at": event.updated_at.isoformat() if event.updated_at else None,
        }
