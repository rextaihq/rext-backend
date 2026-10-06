"""
LemonSqueezy Webhook Service

This service handles all incoming webhooks from LemonSqueezy including:
- Signature verification
- Idempotency checking (prevent duplicate processing)
- Event logging to database
- Event routing to appropriate handlers
- Error handling and retry logic
- Transaction management



Architecture:
    1. Verify webhook signature (security)
    2. Check idempotency (prevent duplicates)
    3. Log event to database
    4. Route to appropriate handler
    5. Mark as processed or failed

Usage:
    webhook_service = LemonSqueezyWebhookService(db_session)
    await webhook_service.process_webhook(payload, signature)

Security:
    - Always verify signature before processing
    - Use idempotency to prevent replay attacks
    - Log all webhook attempts for audit trail
"""

from datetime import datetime, timezone
from typing import Any, Callable, Dict, List

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.database.async_database import AsyncSessionLocal
from src.api.models.subscription_models.webhooks import WebhookEvent
from src.config.payment_config import payment_settings
from src.utils.lemonsqueezy_webhook import (
    WebhookParsingError,
    WebhookVerificationError,
    parse_webhook_payload,
    verify_webhook_signature,
)
from src.utils.logger import logger


class WebhookProcessingError(Exception):
    """Raised when webhook processing fails"""

    pass


class LemonSqueezyWebhookService:
    """Service for processing LemonSqueezy webhook events"""

    def __init__(self, db_session: AsyncSession):
        """
        Initialize webhook service.

        Args:
            db_session: SQLAlchemy async session for database operations
        """
        self.db = db_session
        self.webhook_secret = payment_settings.lemonsqueezy_webhook_secret

        # Event handler registry (will be populated by specific handlers)
        self._handlers: Dict[str, Callable] = {}

        logger.info("LemonSqueezyWebhookService initialized")

    async def process_webhook(self, payload: bytes, signature: str) -> Dict[str, Any]:
        """
        Process incoming webhook from LemonSqueezy.

        This is the main entry point for webhook processing. It handles:
        1. Signature verification
        2. Payload parsing
        3. Idempotency checking
        4. Event logging
        5. Event routing
        6. Error handling

        Args:
            payload: Raw webhook payload (bytes)
            signature: Signature from X-Signature header

        Returns:
            Dict with processing result:
                - success: bool
                - event_id: str
                - event_type: str
                - message: str

        Raises:
            WebhookVerificationError: If signature is invalid
            WebhookParsingError: If payload cannot be parsed
            WebhookProcessingError: If event processing fails
        """
        # Step 1: Verify signature
        is_valid = verify_webhook_signature(
            payload=payload, signature=signature, secret=self.webhook_secret
        )

        if not is_valid:
            logger.error("Webhook signature verification failed")
            raise WebhookVerificationError("Invalid webhook signature")

        # Step 2: Parse payload
        try:
            webhook_data = parse_webhook_payload(payload)
        except Exception as e:
            logger.error(f"Failed to parse webhook payload: {str(e)}")
            raise WebhookParsingError(f"Invalid payload: {str(e)}") from e

        event_id = webhook_data.get("event_id")
        event_type = webhook_data.get("event_type")

        logger.info(
            f"Processing webhook event: {event_type}",
            extra={"event_id": event_id, "event_type": event_type},
        )

        # Step 3: Check idempotency
        is_duplicate = await self._check_idempotency(event_id)
        if is_duplicate:
            logger.info(
                f"Duplicate webhook event {event_id} - skipping", extra={"event_id": event_id}
            )
            return {
                "success": True,
                "event_id": event_id,
                "event_type": event_type,
                "message": "Duplicate event - already processed",
            }

        # Step 4: Log event to database
        webhook_event = await self._log_webhook(webhook_data)

        # Step 5: Route to appropriate handler
        try:
            handler_result = await self._route_event(event_type, webhook_data, webhook_event)
            await self._mark_processed(webhook_event)

            logger.info(
                f"Successfully processed webhook {event_id}",
                extra={"event_id": event_id, "event_type": event_type},
            )

            return {
                "success": True,
                "event_id": event_id,
                "event_type": event_type,
                "message": "Event processed successfully",
                "handler_result": handler_result,
            }

        except Exception as e:
            error_message = f"Error processing event: {str(e)}"
            logger.error(
                error_message, extra={"event_id": event_id, "event_type": event_type}, exc_info=True
            )

            await self._mark_failed(webhook_event, error_message)

            # Re-raise for proper HTTP error response
            raise WebhookProcessingError(error_message) from e

    async def record_webhook(self, payload: bytes) -> Dict[str, Any]:
        """
        Store a verified webhook event before it is acknowledged.

        The route answers Lemon Squeezy only once the event is in webhook_events
        (its own transaction, as _log_webhook does), and answers with an error
        when it can't be stored, so Lemon Squeezy sends it again. Processing then
        runs from the stored row (process_recorded), and a row left unprocessed
        is picked up by the reprocessing job.

        Returns:
            Dict with event_id, event_type and duplicate (already stored before).

        Raises:
            WebhookParsingError: If payload cannot be parsed
        """
        try:
            webhook_data = parse_webhook_payload(payload)
        except Exception as e:
            logger.error(f"Failed to parse webhook payload: {str(e)}")
            raise WebhookParsingError(f"Invalid payload: {str(e)}") from e

        event_id = webhook_data.get("event_id")
        event_type = webhook_data.get("event_type")
        duplicate = await self._check_idempotency(event_id)
        if not duplicate:
            await self._log_webhook(webhook_data)
        return {"event_id": event_id, "event_type": event_type, "duplicate": duplicate}

    async def process_recorded(self, event_id: str) -> Dict[str, Any]:
        """
        Run the handler for an event record_webhook() stored.

        Returns:
            Dict with the result and the handler's result (emails to send).

        Raises:
            WebhookProcessingError: If the handler fails (the row is marked failed)
        """
        webhook_event = (
            await self.db.execute(select(WebhookEvent).where(WebhookEvent.event_id == event_id))
        ).scalar_one_or_none()
        if webhook_event is None or webhook_event.processed:
            return {"success": True, "event_id": event_id, "message": "Nothing to process"}

        event_type = webhook_event.event_name
        try:
            handler_result = await self._route_event(
                event_type, self._webhook_data_from_event(webhook_event), webhook_event
            )
            await self._mark_processed(webhook_event)
        except Exception as e:
            error_message = f"Error processing event: {str(e)}"
            logger.error(
                error_message, extra={"event_id": event_id, "event_type": event_type}, exc_info=True
            )
            await self._mark_failed(webhook_event, error_message)
            raise WebhookProcessingError(error_message) from e

        return {
            "success": True,
            "event_id": event_id,
            "event_type": event_type,
            "message": "Event processed successfully",
            "handler_result": handler_result,
        }

    @staticmethod
    def _webhook_data_from_event(webhook_event: WebhookEvent) -> Dict[str, Any]:
        """The parsed webhook data for a stored event."""
        raw_payload = webhook_event.payload or {}
        meta = raw_payload.get("meta", {}) or {}
        # Mirror the shape produced by parse_webhook_payload on the live path so
        # handlers (and get_user_identifier) see the same keys - notably the
        # top-level ``custom_data`` carrying the checkout ``user_id``.
        return {
            "event_id": webhook_event.event_id,
            "event_type": webhook_event.event_name,
            "data": raw_payload.get("data", {}),
            "meta": meta,
            "custom_data": meta.get("custom_data", {}) or {},
            "raw_payload": raw_payload,
            "timestamp": webhook_event.created_at,
        }

    async def reprocess_event(self, webhook_event: WebhookEvent) -> Dict[str, Any]:
        """
        Reprocess a webhook event from the database.

        Args:
            webhook_event: The WebhookEvent model instance to reprocess.

        Returns:
            Dict with result.
        """
        event_type = webhook_event.event_name
        webhook_data = self._webhook_data_from_event(webhook_event)

        await self._route_event(event_type, webhook_data, webhook_event)

        return {
            "success": True,
            "event_id": webhook_event.event_id,
            "message": "Event reprocessed successfully",
        }

    async def _check_idempotency(self, event_id: str) -> bool:
        """
        Check if webhook event has already been processed.

        Queries the webhook_events table to see if this event_id exists.
        This prevents duplicate processing of the same webhook.

        Args:
            event_id: LemonSqueezy webhook event ID

        Returns:
            bool: True if event already exists, False otherwise
        """
        stmt = select(WebhookEvent).where(WebhookEvent.event_id == event_id)
        result = await self.db.execute(stmt)
        existing_event = result.scalar_one_or_none()

        return existing_event is not None

    async def _log_webhook(self, webhook_data: Dict[str, Any]) -> WebhookEvent:
        """
        Log webhook event to database.

        Creates a new WebhookEvent record for audit trail and idempotency.

        Args:
            webhook_data: Parsed webhook data

        Returns:
            WebhookEvent: Created database record

        Raises:
            IntegrityError: If event_id already exists (race condition)
        """
        # IMPORTANT: The webhook event row is persisted in its OWN transaction,
        # independent of the event-processing transaction. This guarantees the
        # event (and later its failure status) survives even if the handler
        # transaction is rolled back. See _mark_failed for the failure side.
        event_id = webhook_data.get("event_id")
        async with AsyncSessionLocal() as bookkeeping_db:
            webhook_event = WebhookEvent(
                event_id=event_id,
                event_name=webhook_data.get("event_type"),
                payload=webhook_data.get("raw_payload", {}),
                processed=False,
                retry_count=0,
                created_at=datetime.now(timezone.utc),
            )
            try:
                bookkeeping_db.add(webhook_event)
                await bookkeeping_db.commit()

                logger.debug(
                    "Logged webhook event to database",
                    extra={"webhook_id": str(webhook_event.id), "event_id": webhook_event.event_id},
                )
                return webhook_event

            except IntegrityError:
                # Race condition - another process already logged this event
                logger.warning(f"Race condition: Event {event_id} already logged", exc_info=True)
                await bookkeeping_db.rollback()
                stmt = select(WebhookEvent).where(WebhookEvent.event_id == event_id)
                result = await bookkeeping_db.execute(stmt)
                return result.scalar_one()

    async def _route_event(
        self, event_type: str, webhook_data: Dict[str, Any], webhook_event: WebhookEvent
    ) -> None:
        """
        Route webhook event to appropriate handler.

        This method delegates to specific handlers based on event type.
        Handlers are registered in self._handlers dict.

        Args:
            event_type: Type of webhook event
            webhook_data: Parsed webhook data
            webhook_event: Database record for this event

        Raises:
            WebhookProcessingError: If no handler found or handler fails
        """
        # Check if handler is registered
        handler = self._handlers.get(event_type)

        if handler:
            logger.debug(f"Routing event {event_type} to handler {handler.__name__}")
            return await handler(webhook_data, webhook_event, self.db)
        else:
            # No handler registered - log warning but don't fail
            logger.warning(
                f"No handler registered for event type: {event_type}",
                extra={"event_type": event_type, "event_id": webhook_data.get("event_id")},
            )

            # For now, we'll just log the event without processing
            # Handlers will be implemented in subsequent tasks (1.3.3 - 1.3.12)

    async def _mark_processed(self, webhook_event: WebhookEvent) -> None:
        """
        Mark webhook event as successfully processed.

        Args:
            webhook_event: Database record to update
        """
        now = datetime.now(timezone.utc)

        # Update the status on the processing session so it commits atomically
        # with the handler's work (preserves existing success semantics).
        await self.db.execute(
            update(WebhookEvent)
            .where(WebhookEvent.id == webhook_event.id)
            .values(processed=True, processed_at=now, error_message=None, updated_at=now)
        )
        await self.db.flush()

        # Reflect on the in-memory (possibly detached) instance for callers.
        webhook_event.processed = True
        webhook_event.processed_at = now
        webhook_event.error_message = None

        logger.debug(
            "Marked webhook event as processed", extra={"event_id": webhook_event.event_id}
        )

    async def _mark_failed(self, webhook_event: WebhookEvent, error_message: str) -> None:
        """
        Mark webhook event as failed with error message.

        Args:
            webhook_event: Database record to update
            error_message: Error description
        """
        # Persist the failure in its OWN transaction so it is retained even when
        # the processing transaction (self.db) is rolled back by the caller.
        now = datetime.now(timezone.utc)
        new_retry_count = webhook_event.retry_count or 0
        async with AsyncSessionLocal() as bookkeeping_db:
            row = await bookkeeping_db.get(WebhookEvent, webhook_event.id)
            if row is not None:
                row.processed = False
                row.error_message = error_message
                row.retry_count = (row.retry_count or 0) + 1
                row.processed_at = None
                row.updated_at = now
                await bookkeeping_db.commit()
                new_retry_count = row.retry_count

        # Reflect on the in-memory instance for callers.
        webhook_event.processed = False
        webhook_event.error_message = error_message
        webhook_event.retry_count = new_retry_count

        logger.error(
            f"Marked webhook event as failed (retry {webhook_event.retry_count})",
            extra={
                "event_id": webhook_event.event_id,
                "error": error_message,
                "retry_count": webhook_event.retry_count,
            },
        )

    def register_handler(self, event_type: str, handler: Callable) -> None:
        """
        Register a handler function for a specific event type.

        This allows extending the service with custom handlers for each
        webhook event type (subscription_created, order_created, etc.)

        Args:
            event_type: LemonSqueezy event type (e.g., "subscription_created")
            handler: Async function to handle the event

        Example:
            async def handle_subscription_created(webhook_data, webhook_event):
                # Process subscription creation
                pass

            service.register_handler(
                WebhookEventTypes.SUBSCRIPTION_CREATED,
                handle_subscription_created
            )
        """
        self._handlers[event_type] = handler
        logger.info(f"Registered handler for event type: {event_type}")

    async def retry_failed_event(self, event_id: str) -> Dict[str, Any]:
        """
        Retry processing a failed webhook event.

        Useful for manual retry of failed events or scheduled retry jobs.

        Args:
            event_id: LemonSqueezy webhook event ID

        Returns:
            Dict with retry result

        Raises:
            WebhookProcessingError: If event not found or retry fails
        """
        # Retrieve failed event
        stmt = select(WebhookEvent).where(WebhookEvent.event_id == event_id)
        result = await self.db.execute(stmt)
        webhook_event = result.scalar_one_or_none()

        if not webhook_event:
            raise WebhookProcessingError(f"Webhook event {event_id} not found")

        if webhook_event.processed:
            return {"success": True, "message": "Event already processed", "event_id": event_id}

        logger.info(
            f"Retrying failed webhook event {event_id}",
            extra={"event_id": event_id, "retry_count": webhook_event.retry_count},
        )

        # Parse payload from database
        try:
            webhook_data = {
                "event_id": webhook_event.event_id,
                "event_type": webhook_event.event_name,
                "data": webhook_event.payload.get("data", {}),
                "custom_data": webhook_event.payload.get("meta", {}).get("custom_data", {}),
                "raw_payload": webhook_event.payload,
                "timestamp": webhook_event.created_at,
            }

            # Route to handler
            await self._route_event(webhook_event.event_name, webhook_data, webhook_event)

            await self._mark_processed(webhook_event)

            return {"success": True, "message": "Event retried successfully", "event_id": event_id}

        except Exception as e:
            error_message = f"Retry failed: {str(e)}"
            await self._mark_failed(webhook_event, error_message)
            raise WebhookProcessingError(error_message) from e

    async def get_failed_events(self, limit: int = 100, max_retries: int = 3) -> List[WebhookEvent]:
        """
        Get list of failed webhook events that can be retried.

        Args:
            limit: Maximum number of events to return
            max_retries: Only return events with retry_count < max_retries

        Returns:
            List of failed WebhookEvent records
        """
        stmt = (
            select(WebhookEvent)
            .where(WebhookEvent.processed.is_(False), WebhookEvent.retry_count < max_retries)
            .order_by(WebhookEvent.created_at.desc())
            .limit(limit)
        )

        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def get_event_stats(self) -> Dict[str, Any]:
        """
        Get statistics about webhook processing.

        Returns:
            Dict with stats:
                - total_events: Total webhook events received
                - processed_events: Successfully processed events
                - failed_events: Failed events
                - pending_retries: Events that can be retried
        """
        from sqlalchemy import func

        # Total events
        total_stmt = select(func.count(WebhookEvent.id))
        total_result = await self.db.execute(total_stmt)
        total = total_result.scalar()

        # Processed events
        processed_stmt = select(func.count(WebhookEvent.id)).where(WebhookEvent.processed.is_(True))
        processed_result = await self.db.execute(processed_stmt)
        processed = processed_result.scalar()

        # Failed events
        failed_stmt = select(func.count(WebhookEvent.id)).where(WebhookEvent.processed.is_(False))
        failed_result = await self.db.execute(failed_stmt)
        failed = failed_result.scalar()

        # Pending retries (failed with retry_count < 3)
        pending_stmt = select(func.count(WebhookEvent.id)).where(
            WebhookEvent.processed.is_(False), WebhookEvent.retry_count < 3
        )
        pending_result = await self.db.execute(pending_stmt)
        pending = pending_result.scalar()

        return {
            "total_events": total or 0,
            "processed_events": processed or 0,
            "failed_events": failed or 0,
            "pending_retries": pending or 0,
            "success_rate": round((processed / total * 100) if total else 0, 2),
        }
