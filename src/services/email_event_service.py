"""
Email Event Service - Business Logic for Webhook Processing

Handles incoming webhook events from Resend:
- Creates EmailEvent records
- Updates EmailLog status based on events
- Handles duplicate events (idempotent)
- Correlates events to email logs via provider_message_id
"""
from typing import Optional, Dict, Any
from uuid import UUID
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.api.models.email_models.email_event import EmailEvent
from src.api.models.email_models.email_log import EmailLog
from src.api.schema.webhook_schema import (
    ResendWebhookRequest,
    WebhookProcessingResult
)
from src.api.lib.logger import auto_logger

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

    def __init__(self, db: AsyncSession):
        """
        Initialize Email Event Service.

        Args:
            db: Async SQLAlchemy database session
        """
        self.db = db

    async def process_webhook_event(
        self,
        webhook_payload: Dict[str, Any]
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

            event_type = webhook.type
            event_data = webhook.data
            created_at_str = webhook.created_at

            # Extract email ID from event data
            email_id = event_data.get("email_id")
            if not email_id:
                logger.warning(
                    "Webhook event missing email_id",
                    extra={"event_type": event_type, "data": event_data}
                )
                return WebhookProcessingResult(
                    success=False,
                    message="Missing email_id in webhook data",
                    event_type=event_type
                )

            logger.info(
                "Processing webhook event",
                extra={
                    "event_type": event_type,
                    "email_id": email_id,
                    "created_at": created_at_str
                }
            )

            # Check if event already processed (idempotency)
            existing_event = await self._find_event_by_provider_id(email_id, event_type, created_at_str)
            if existing_event:
                logger.info(
                    "Duplicate webhook event ignored",
                    extra={
                        "event_id": str(existing_event.id),
                        "event_type": event_type,
                        "email_id": email_id
                    }
                )
                return WebhookProcessingResult(
                    success=True,
                    event_id=str(existing_event.id),
                    message="Event already processed (duplicate)",
                    event_type=event_type
                )

            # Find corresponding email log
            email_log = await self._find_email_log_by_message_id(email_id)

            if not email_log:
                logger.warning(
                    "Email log not found for webhook event",
                    extra={"email_id": email_id, "event_type": event_type}
                )
                # Still create event record for tracking, but without log linkage
                email_log_id = None
            else:
                email_log_id = email_log.id
                logger.debug(
                    "Found email log for event",
                    extra={
                        "email_log_id": str(email_log.id),
                        "email_id": email_id
                    }
                )

            # Parse created_at timestamp
            try:
                event_timestamp = datetime.fromisoformat(created_at_str.replace('Z', '+00:00'))
            except (ValueError, AttributeError):
                logger.warning(
                    f"Invalid timestamp format: {created_at_str}",
                    extra={"event_type": event_type}
                )
                event_timestamp = datetime.now(timezone.utc)

            # Create event record
            email_event = EmailEvent(
                email_log_id=email_log_id,
                provider="resend",
                provider_event_id=f"{email_id}_{event_type}_{created_at_str}",  # Unique composite ID
                provider_message_id=email_id,
                event_type=event_type,
                event_data=event_data,
                received_at=datetime.now(timezone.utc),
                created_at=event_timestamp
            )

            self.db.add(email_event)
            await self.db.flush()

            logger.info(
                "Email event created",
                extra={
                    "event_id": str(email_event.id),
                    "event_type": event_type,
                    "email_log_id": str(email_log_id) if email_log_id else None
                }
            )

            # Update email log status based on event type
            if email_log:
                await self._update_email_log_status(email_log, event_type, event_timestamp)

            await self.db.flush()

            return WebhookProcessingResult(
                success=True,
                event_id=str(email_event.id),
                email_log_id=str(email_log_id) if email_log_id else None,
                message="Event processed successfully",
                event_type=event_type
            )

        except Exception as e:
            logger.error(
                f"Failed to process webhook event: {str(e)}",
                extra={
                    "error_type": type(e).__name__,
                    "payload": webhook_payload
                },
                exc_info=True
            )
            await self.db.rollback()

            return WebhookProcessingResult(
                success=False,
                message=f"Error processing event: {str(e)}",
                event_type=webhook_payload.get("type", "unknown")
            )

    async def _find_event_by_provider_id(
        self,
        email_id: str,
        event_type: str,
        created_at: str
    ) -> Optional[EmailEvent]:
        """
        Find existing event by provider composite ID.

        Args:
            email_id: Provider's email/message ID
            event_type: Event type
            created_at: Event timestamp

        Returns:
            EmailEvent if found, None otherwise
        """
        provider_event_id = f"{email_id}_{event_type}_{created_at}"

        result = await self.db.execute(
            select(EmailEvent).where(
                EmailEvent.provider_event_id == provider_event_id
            )
        )
        return result.scalar_one_or_none()

    async def _find_email_log_by_message_id(
        self,
        provider_message_id: str
    ) -> Optional[EmailLog]:
        """
        Find email log by provider message ID.

        Args:
            provider_message_id: Provider's message/email ID

        Returns:
            EmailLog if found, None otherwise
        """
        result = await self.db.execute(
            select(EmailLog).where(
                EmailLog.provider_message_id == provider_message_id
            )
        )
        return result.scalar_one_or_none()

    async def _update_email_log_status(
        self,
        email_log: EmailLog,
        event_type: str,
        event_timestamp: datetime
    ):
        """
        Update email log status based on webhook event type.

        Args:
            email_log: EmailLog to update
            event_type: Type of event received
            event_timestamp: When event occurred

        Status transitions:
        - email.sent -> status="sent"
        - email.delivered -> status="delivered", delivered_at
        - email.bounced -> status="bounced", failed_at
        - email.complained -> status="complained"
        - email.opened -> (no status change, just tracking)
        - email.clicked -> (no status change, just tracking)
        """
        original_status = email_log.status

        if event_type == "email.sent":
            # Already handled by email service
            pass

        elif event_type == "email.delivered":
            email_log.status = "delivered"
            email_log.delivered_at = event_timestamp

        elif event_type == "email.delivery_delayed":
            # Keep current status but log delay
            logger.info(
                "Email delivery delayed",
                extra={
                    "email_log_id": str(email_log.id),
                    "to": email_log.to_email
                }
            )

        elif event_type == "email.bounced":
            email_log.status = "bounced"
            email_log.failed_at = event_timestamp
            # Extract bounce reason from event data
            bounce_data = email_log.provider_response or {}
            bounce_data["bounce_event"] = event_timestamp.isoformat()
            email_log.provider_response = bounce_data

        elif event_type == "email.complained":
            email_log.status = "complained"
            # User marked as spam
            logger.warning(
                "Email marked as spam",
                extra={
                    "email_log_id": str(email_log.id),
                    "to": email_log.to_email
                }
            )

        elif event_type in ["email.opened", "email.clicked"]:
            # These don't change status, just tracking events
            pass

        else:
            logger.warning(
                f"Unknown event type: {event_type}",
                extra={"email_log_id": str(email_log.id)}
            )

        # Update timestamp
        email_log.updated_at = datetime.now(timezone.utc)

        if email_log.status != original_status:
            logger.info(
                "Email log status updated",
                extra={
                    "email_log_id": str(email_log.id),
                    "old_status": original_status,
                    "new_status": email_log.status,
                    "event_type": event_type
                }
            )

    async def get_events_for_email_log(
        self,
        email_log_id: UUID,
        limit: int = 50
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

    async def get_recent_events(
        self,
        hours: int = 24,
        limit: int = 100
    ) -> list[EmailEvent]:
        """
        Get recent email events.

        Args:
            hours: Number of hours to look back
            limit: Maximum number of events

        Returns:
            List of EmailEvent records
        """
        from datetime import timedelta

        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours)

        result = await self.db.execute(
            select(EmailEvent)
            .where(EmailEvent.received_at >= cutoff_time)
            .order_by(EmailEvent.received_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
