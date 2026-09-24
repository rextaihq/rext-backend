"""
Email Event Service - Business Logic for Webhook Processing

Handles incoming webhook events from Resend:
- Creates EmailEvent records for delivery, opens, and clicks
- Updates EmailLog status based on provider events
- Handles duplicate events (idempotent)
- Correlates events to email logs via provider_message_id and internal UUID
"""

import hashlib
import re
from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.lib.logger import auto_logger
from src.api.models.email_models.email_event import EmailEvent
from src.api.models.email_models.email_log import EmailLog
from src.api.schema.webhook_schema import ResendWebhookRequest, WebhookProcessingResult
from src.utils.datetime_utils import parse_iso_datetime, utc_now

logger = auto_logger()


class EmailEventService:
    """
    Service for processing email webhook events.

    Handles:
    - Event validation and deduplication
    - Email log status updates
    - Event storage in database
    - Idempotent processing
    """

    # Canonical, provider-agnostic event type names. These are what gets stored
    # in EmailEvent.event_type and what EmailAnalyticsService queries against.
    # Resend delivers event types prefixed with "email." (e.g. "email.opened");
    # we strip that prefix on ingestion so the stored value matches the model
    # contract (see EmailEvent.event_type) and the analytics queries.
    _EVENT_TYPE_PREFIX = "email."

    def __init__(self, db: AsyncSession):
        """
        Initialize Email Event Service.

        Args:
            db: Async SQLAlchemy database session
        """
        self.db = db

    @classmethod
    def _normalize_event_type(cls, event_type: Optional[str]) -> str:
        """
        Strip the provider "email." prefix so stored event types are canonical.

        "email.opened" -> "opened", "email.delivered" -> "delivered", etc.
        Values without the prefix are returned unchanged.
        """
        if event_type and event_type.startswith(cls._EVENT_TYPE_PREFIX):
            return event_type[len(cls._EVENT_TYPE_PREFIX) :]
        return event_type or ""

    def _generate_provider_event_id(
        self, email_id: str, event_type: str, created_at_str: str
    ) -> str:
        """
        Generate deterministic, normalized idempotency key for webhook events.

        Uses SHA-256 hash of normalized components to produce fixed-length key
        immune to minor format changes in source data.

        Args:
            email_id: Provider's email/message ID
            event_type: Event type (e.g., "email.delivered")
            created_at_str: Raw timestamp string from webhook

        Returns:
            Deterministic event ID string prefixed with "evt_"
        """
        # Normalize timestamp: parse to datetime and format consistently
        try:
            parsed_ts = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
            normalized_ts = parsed_ts.strftime("%Y-%m-%dT%H:%M:%S")
        except (ValueError, AttributeError):
            # Fallback: use raw string if parsing fails
            normalized_ts = created_at_str

        # Use pipe delimiter to avoid collision with values containing underscores
        content = f"{email_id}|{event_type}|{normalized_ts}"
        hash_value = hashlib.sha256(content.encode("utf-8")).hexdigest()[:32]
        return f"evt_{hash_value}"

    async def process_webhook_event(
        self, webhook_payload: Dict[str, Any]
    ) -> WebhookProcessingResult:
        """
        Process incoming webhook event from Resend.

        Args:
            webhook_payload: Raw webhook payload from Resend

        Returns:
            WebhookProcessingResult with processing status

        Note:
            - Idempotent: Duplicate events are ignored
            - Updates email log status based on event type
            - Stores full event data for analytics
        """
        try:
            # Parse webhook payload
            webhook = ResendWebhookRequest(**webhook_payload)

            raw_event_type = webhook.type
            event_type = self._normalize_event_type(raw_event_type)
            event_data = webhook.data
            created_at_str = webhook.created_at

            # Extract email ID from event data
            email_id = event_data.get("email_id") or event_data.get("id")
            if not email_id and isinstance(webhook_payload.get("data"), dict):
                email_id = webhook_payload["data"].get("email_id") or webhook_payload["data"].get(
                    "id"
                )

            if not email_id:
                logger.warning(
                    "Webhook event missing email_id",
                    extra={"event_type": event_type, "data": event_data},
                )
                return WebhookProcessingResult(
                    success=False, message="Missing email_id in webhook data", event_type=event_type
                )

            logger.info(
                "Processing webhook event",
                extra={
                    "event_type": event_type,
                    "email_id": email_id,
                    "created_at": created_at_str,
                },
            )

            # Check if event already processed (idempotency)
            existing_event = await self._find_event_by_provider_id(
                email_id, event_type, created_at_str
            )
            if existing_event:
                logger.info(
                    "Duplicate webhook event ignored",
                    extra={
                        "event_id": str(existing_event.id),
                        "event_type": event_type,
                        "email_id": email_id,
                    },
                )
                return WebhookProcessingResult(
                    success=True,
                    event_id=str(existing_event.id),
                    message="Event already processed (duplicate)",
                    event_type=event_type,
                )

            # Extract recipient email if available
            to_raw = event_data.get("to") if isinstance(event_data, dict) else None
            to_email = (
                to_raw[0]
                if isinstance(to_raw, list) and to_raw
                else (to_raw if isinstance(to_raw, str) else None)
            )

            # Find corresponding email log
            email_log = await self._find_email_log_by_message_id(email_id, to_email)

            if not email_log:
                logger.warning(
                    "Email log not found for webhook event",
                    extra={"email_id": email_id, "event_type": event_type},
                )
                # Still create event record for tracking, but without log linkage
                email_log_id = None
            else:
                email_log_id = email_log.id
                logger.debug(
                    "Found email log for event",
                    extra={"email_log_id": str(email_log.id), "email_id": email_id},
                )

            # Parse created_at timestamp
            try:
                event_timestamp = parse_iso_datetime(created_at_str)
            except (ValueError, AttributeError):
                logger.warning(
                    f"Invalid timestamp format: {created_at_str}", extra={"event_type": event_type}
                )
                event_timestamp = utc_now()

            # Preserve the provider's raw event type for traceability without
            # polluting the canonical event_type column.
            if isinstance(event_data, dict) and raw_event_type != event_type:
                event_data = {**event_data, "_raw_event_type": raw_event_type}

            # Create event record
            email_event = EmailEvent(
                email_log_id=email_log_id,
                provider="resend",
                provider_event_id=self._generate_provider_event_id(
                    email_id, event_type, created_at_str
                ),
                provider_message_id=email_id,
                event_type=event_type,
                event_data=event_data,
                received_at=utc_now(),
                created_at=event_timestamp,
            )

            self.db.add(email_event)
            await self.db.flush()

            logger.info(
                "Email event created",
                extra={
                    "event_id": str(email_event.id),
                    "event_type": event_type,
                    "email_log_id": str(email_log_id) if email_log_id else None,
                },
            )

            # Update email log status based on event type
            if email_log:
                await self._update_email_log_status(
                    email_log, event_type, event_timestamp, event_data
                )

            await self.db.flush()

            return WebhookProcessingResult(
                success=True,
                event_id=str(email_event.id),
                email_log_id=str(email_log_id) if email_log_id else None,
                message="Event processed successfully",
                event_type=event_type,
            )

        except Exception as e:
            logger.error(
                f"Failed to process webhook event: {str(e)}",
                extra={"error_type": type(e).__name__, "payload": webhook_payload},
                exc_info=True,
            )
            await self.db.rollback()

            return WebhookProcessingResult(
                success=False,
                message=f"Error processing event: {str(e)}",
                event_type=webhook_payload.get("type", "unknown"),
            )

    async def _find_event_by_provider_id(
        self, email_id: str, event_type: str, created_at: str
    ) -> Optional[EmailEvent]:
        """
        Find existing event by provider composite ID.

        Args:
            email_id: Provider's email/message ID
            event_type: Event type
            created_at: Event timestamp string

        Returns:
            EmailEvent if found, None otherwise
        """
        provider_event_id = self._generate_provider_event_id(email_id, event_type, created_at)

        result = await self.db.execute(
            select(EmailEvent).where(EmailEvent.provider_event_id == provider_event_id)
        )
        return result.scalar_one_or_none()

    async def _find_email_log_by_message_id(
        self, provider_message_id: str, to_email: Optional[str] = None
    ) -> Optional[EmailLog]:
        """
        Find email log by provider message ID, internal UUID, or recipient email fallback.

        Args:
            provider_message_id: Provider's message/email ID
            to_email: Optional recipient email for fallback correlation

        Returns:
            EmailLog if found, None otherwise
        """
        if provider_message_id:
            from sqlalchemy import String, cast

            result = await self.db.execute(
                select(EmailLog).where(
                    or_(
                        EmailLog.provider_message_id == provider_message_id,
                        cast(EmailLog.id, String) == str(provider_message_id),
                    )
                )
            )
            log = result.scalar_one_or_none()
            if log:
                return log

        # Fallback to recipient email
        if to_email:
            from sqlalchemy import desc

            result = await self.db.execute(
                select(EmailLog)
                .where(EmailLog.to_email == to_email)
                .order_by(desc(EmailLog.created_at))
                .limit(1)
            )
            return result.scalar_one_or_none()

        return None

    @staticmethod
    def _extract_bounce_reason(event_data: Optional[dict]) -> Optional[str]:
        """Pull a human-readable bounce reason out of a Resend bounce payload.

        Resend has shipped a few shapes over time:
        - nested: data.bounce = {"message", "subType", "type", "diagnosticCode"}
        - flat:   data.bounce_reason / data.bounce_type

        The nested `message` is often generic SES boilerplate, so the raw SMTP
        `diagnosticCode` (e.g. "550 5.1.1 ... does not exist") is preferred when
        present because it names the actual cause.
        """
        if not isinstance(event_data, dict):
            return None

        bounce = event_data.get("bounce")
        if isinstance(bounce, dict):
            message = bounce.get("message") or bounce.get("description")
            btype = bounce.get("type")
            subtype = bounce.get("subType") or bounce.get("sub_type")
            parts = [p for p in (btype, subtype) if p]
            prefix = f"[{'/'.join(parts)}] " if parts else ""

            diag = bounce.get("diagnosticCode") or bounce.get("diagnostic_code")
            if isinstance(diag, (list, tuple)):
                diag = next((d for d in diag if isinstance(d, str) and d.strip()), None)
            if isinstance(diag, str) and diag.strip():
                # Collapse the wrapped "550-5.1.1 ...550-5.1.1 ..." SMTP continuation
                clean = re.sub(r"\s+", " ", diag).strip()
                clean = re.sub(r"^smtp;\s*", "", clean, flags=re.IGNORECASE)
                # Drop the repeated "550-5.1.1"/"550 5.1.1" SMTP status that Gmail
                # interleaves into every wrapped line of the diagnostic text.
                clean = re.sub(r"\s*\d{3}[- ]\d\.\d\.\d\s*", " ", clean).strip()
                clean = re.sub(r"\s{2,}", " ", clean)
                if len(clean) > 300:
                    clean = clean[:297].rstrip() + "..."
                return f"{prefix}{clean}".strip()

            if message:
                return f"{prefix}{message}".strip()
            if parts:
                return prefix.strip()
        elif isinstance(bounce, str) and bounce.strip():
            return bounce.strip()

        reason = event_data.get("bounce_reason")
        btype = event_data.get("bounce_type")
        if reason:
            return f"[{btype}] {reason}".strip() if btype else str(reason)
        return None

    async def _update_email_log_status(
        self,
        email_log: EmailLog,
        event_type: str,
        event_timestamp: datetime,
        event_data: Optional[dict] = None,
    ):
        """
        Update email log status based on webhook event type.

        Args:
            email_log: EmailLog to update
            event_type: Canonical (prefix-stripped) type of event received
            event_timestamp: When event occurred

        Status transitions:
        - sent -> status="sent"
        - delivered -> status="delivered", delivered_at
        - bounced -> status="bounced", failed_at
        - complained -> status="complained"
        - opened -> (no status change, just tracking)
        - clicked -> (no status change, just tracking)
        """
        original_status = email_log.status

        if event_type == "sent":
            # Already handled by email service
            pass

        elif event_type == "delivered":
            email_log.status = "delivered"
            email_log.delivered_at = event_timestamp

        elif event_type == "delivery_delayed":
            # Keep current status but log delay
            logger.info(
                "Email delivery delayed",
                extra={"email_log_id": str(email_log.id), "to": email_log.to_email},
            )

        elif event_type == "bounced":
            email_log.status = "bounced"
            email_log.failed_at = event_timestamp
            # Extract bounce reason from event data
            bounce_data = email_log.provider_response or {}
            bounce_data["bounce_event"] = event_timestamp.isoformat()
            bounce_reason = self._extract_bounce_reason(event_data)
            if bounce_reason:
                bounce_data["bounce_reason"] = bounce_reason
                email_log.error_message = bounce_reason
            else:
                email_log.error_message = (
                    email_log.error_message or "Email bounced (no reason provided by provider)"
                )
            email_log.provider_response = bounce_data

        elif event_type == "complained":
            email_log.status = "complained"
            # User marked as spam
            logger.warning(
                "Email marked as spam",
                extra={"email_log_id": str(email_log.id), "to": email_log.to_email},
            )

        elif event_type in ["opened", "clicked"]:
            # An opened or clicked email was delivered
            if email_log.status in ["sent", "queued"]:
                email_log.status = "delivered"
                if not email_log.delivered_at:
                    email_log.delivered_at = event_timestamp

        else:
            logger.warning(
                f"Unknown event type: {event_type}", extra={"email_log_id": str(email_log.id)}
            )

        # Update timestamp
        email_log.updated_at = utc_now()

        if email_log.status != original_status:
            logger.info(
                "Email log status updated",
                extra={
                    "email_log_id": str(email_log.id),
                    "old_status": original_status,
                    "new_status": email_log.status,
                    "event_type": event_type,
                },
            )

    async def get_events_for_email_log(
        self, email_log_id: UUID, limit: int = 50
    ) -> list[EmailEvent]:
        """
        Get all events for a specific email log.

        Args:
            email_log_id: Email log UUID
            limit: Maximum number of events to return

        Returns:
            List of EmailEvent records
        """
        result = await self.db.execute(
            select(EmailEvent)
            .where(EmailEvent.email_log_id == email_log_id)
            .order_by(EmailEvent.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_recent_events(self, hours: int = 24, limit: int = 100) -> list[EmailEvent]:
        """
        Get recent email events.

        Args:
            hours: Number of hours to look back
            limit: Maximum number of events

        Returns:
            List of EmailEvent records
        """
        from datetime import timedelta

        cutoff_time = utc_now() - timedelta(hours=hours)

        result = await self.db.execute(
            select(EmailEvent)
            .where(EmailEvent.received_at >= cutoff_time)
            .order_by(EmailEvent.received_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
