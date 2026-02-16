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

from typing import Dict, Any, Optional, Callable, List
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from src.api.models.subscription_models.webhooks import WebhookEvent
from src.utils.lemonsqueezy_webhook import (
    verify_webhook_signature,
    parse_webhook_payload,
    extract_subscription_data,
    extract_order_data,
    extract_license_key_data,
    get_user_identifier,
    WebhookEventTypes,
    WebhookVerificationError,
    WebhookParsingError
)
from src.utils.logger import logger
from src.config.payment_config import payment_settings


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

    async def process_webhook(
        self,
        payload: bytes,
        signature: str
    ) -> Dict[str, Any]:
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
            payload=payload,
            signature=signature,
            secret=self.webhook_secret
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
            extra={"event_id": event_id, "event_type": event_type}
        )

        # Step 3: Check idempotency
        is_duplicate = await self._check_idempotency(event_id)
        if is_duplicate:
            logger.info(
                f"Duplicate webhook event {event_id} - skipping",
                extra={"event_id": event_id}
            )
            return {
                "success": True,
                "event_id": event_id,
                "event_type": event_type,
                "message": "Duplicate event - already processed"
            }

        # Step 4: Log event to database
        webhook_event = await self._log_webhook(webhook_data)

        # Step 5: Route to appropriate handler
        try:
            await self._route_event(event_type, webhook_data, webhook_event)
            await self._mark_processed(webhook_event)

            logger.info(
                f"Successfully processed webhook {event_id}",
                extra={"event_id": event_id, "event_type": event_type}
            )

            return {
                "success": True,
                "event_id": event_id,
                "event_type": event_type,
                "message": "Event processed successfully"
            }

        except Exception as e:
            error_message = f"Error processing event: {str(e)}"
            logger.error(
                error_message,
                extra={"event_id": event_id, "event_type": event_type},
                exc_info=True
            )

            await self._mark_failed(webhook_event, error_message)

            # Re-raise for proper HTTP error response
            raise WebhookProcessingError(error_message) from e

    async def reprocess_event(
        self,
        event_name: str,
        payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Reprocess a previously-received webhook event.

        This skips signature verification and idempotency checks since the event
        was already verified on initial receipt. Used for admin retry operations.

        Args:
            event_name: The webhook event name (e.g., "subscription_created")
            payload: The parsed webhook payload (dict)

        Returns:
            Dict with processing result
        """
        logger.info(f"Reprocessing webhook event: {event_name}")

        # Route to appropriate handler
        handler = self._handlers.get(event_name)
        if handler:
            # Create a minimal mock event object if needed by handlers, 
            # or update existing handlers to be flexible.
            # Assuming handlers take (webhook_data, webhook_event, db)
            # We need to fetch or mock the event object if handlers rely on it.
            # However, for retry logic in monitoring service, we might already have the event object.
            # But here we are designing a method that takes payload.
            
            # Since handlers might expect a WebhookEvent object and we don't have it passed here,
            # we should update the signature or retrieval strategy.
            # BUT, to keep changes minimal and safe as requested:
            # We will use the internal _route_event which expects a WebhookEvent.
            # The monitoring service calling this has the event.
            # Let's update the signature to accept the event object OR fetch it.
            # Actually, the monitoring service has the event object and calls this.
            # Let's follow the plan and route to handler directly.
            
            # Wait, _route_event takes (event_type, webhook_data, webhook_event).
            # So this method should probably take the event object or ID to allow fetching/passing it.
            pass
        
        # Re-reading requirements: "The retry should reprocess the stored event data directly... 
        # bypassing signature verification... route directly to the handler routing."
        
        # Let's implement it to take event_name and payload as requested, 
        # but we also need the webhook_event object for _route_event if we reuse it.
        # The monitoring service has it.
        # Let's updated the method signature to accept the webhook_event if possible, 
        # or find it by ID if passed.
        
        # Simpler approach matching the plan's suggestion:
        # Route to handler directly if it exists.
        if handler:
             # We need to construct webhook_data from payload if not already in that format.
             # The payload stored in DB is usually the "raw_payload" or parsed dict.
             # Let's assume payload is the dictionary suitable for handlers.
             
             # Wait, handlers signature is: await handler(webhook_data, webhook_event, self.db)
             # We are missing webhook_event here.
             pass

    # Correcting implementation based on the fact that existing _route_event needs webhook_event.
    # We will modify reprocess_event to take the event_id and fetch it, OR take the event object.
    # The monitoring service has the event object.
    # Let's make reprocess_event take (webhook_event: WebhookEvent). 
    # But the plan proposed: reprocess_event(event_name, payload).
        
    # Let's look at _route_event signature again:
    # async def _route_event(self, event_type: str, webhook_data: Dict[str, Any], webhook_event: WebhookEvent) -> None
    
    # So we definitely need the webhook_event. 
    # Let's implement reprocess_event to accept it.
    
    async def reprocess_event(
        self,
        webhook_event: WebhookEvent
    ) -> Dict[str, Any]:
        """
        Reprocess a webhook event from the database.
        
        Args:
            webhook_event: The WebhookEvent model instance to reprocess.
            
        Returns:
            Dict with result.
        """
        event_type = webhook_event.event_name
        # Reconstruct webhook_data from the stored payload
        # The stored payload is likely the raw payload or a dict.
        # If it's a dict, we can likely use it directly or wrap it.
        webhook_data = {
            "event_id": webhook_event.event_id,
            "event_type": event_type,
            "data": webhook_event.payload.get("data", {}),
            "meta": webhook_event.payload.get("meta", {}),
             # specific handlers might rely on 'raw_payload' key if they parse it again?
             # lemon squeezy handlers usually work with the parsed structure.
        }
        
        await self._route_event(event_type, webhook_data, webhook_event)
        
        return {
            "success": True, 
            "event_id": webhook_event.event_id, 
            "message": "Event reprocessed successfully"
        }
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
        webhook_event = WebhookEvent(
            event_id=webhook_data.get("event_id"),
            event_name=webhook_data.get("event_type"),
            payload=webhook_data.get("raw_payload", {}),
            processed=False,
            retry_count=0,
            created_at=datetime.now(timezone.utc)
        )

        try:
            self.db.add(webhook_event)
            await self.db.flush()  # Get the ID without committing

            logger.debug(
                f"Logged webhook event to database",
                extra={
                    "webhook_id": str(webhook_event.id),
                    "event_id": webhook_event.event_id
                }
            )

            return webhook_event

        except IntegrityError as e:
            # Race condition - another process already logged this event
            logger.warning(
                f"Race condition: Event {webhook_data.get('event_id')} already logged",
                exc_info=True
            )
            await self.db.rollback()

            # Retrieve the existing event
            stmt = select(WebhookEvent).where(
                WebhookEvent.event_id == webhook_data.get("event_id")
            )
            result = await self.db.execute(stmt)
            return result.scalar_one()

    async def _route_event(
        self,
        event_type: str,
        webhook_data: Dict[str, Any],
        webhook_event: WebhookEvent
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
            await handler(webhook_data, webhook_event, self.db)
        else:
            # No handler registered - log warning but don't fail
            logger.warning(
                f"No handler registered for event type: {event_type}",
                extra={
                    "event_type": event_type,
                    "event_id": webhook_data.get("event_id")
                }
            )

            # For now, we'll just log the event without processing
            # Handlers will be implemented in subsequent tasks (1.3.3 - 1.3.12)

    async def _mark_processed(self, webhook_event: WebhookEvent) -> None:
        """
        Mark webhook event as successfully processed.

        Args:
            webhook_event: Database record to update
        """
        webhook_event.processed = True
        webhook_event.processed_at = datetime.now(timezone.utc)
        webhook_event.error_message = None

        await self.db.flush()

        logger.debug(
            f"Marked webhook event as processed",
            extra={"event_id": webhook_event.event_id}
        )

    async def _mark_failed(
        self,
        webhook_event: WebhookEvent,
        error_message: str
    ) -> None:
        """
        Mark webhook event as failed with error message.

        Args:
            webhook_event: Database record to update
            error_message: Error description
        """
        webhook_event.processed = False
        webhook_event.error_message = error_message
        webhook_event.retry_count += 1

        await self.db.flush()

        logger.error(
            f"Marked webhook event as failed (retry {webhook_event.retry_count})",
            extra={
                "event_id": webhook_event.event_id,
                "error": error_message,
                "retry_count": webhook_event.retry_count
            }
        )

    def register_handler(
        self,
        event_type: str,
        handler: Callable
    ) -> None:
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
            return {
                "success": True,
                "message": "Event already processed",
                "event_id": event_id
            }

        logger.info(
            f"Retrying failed webhook event {event_id}",
            extra={
                "event_id": event_id,
                "retry_count": webhook_event.retry_count
            }
        )

        # Parse payload from database
        try:
            webhook_data = {
                "event_id": webhook_event.event_id,
                "event_type": webhook_event.event_name,
                "data": webhook_event.payload.get("data", {}),
                "custom_data": webhook_event.payload.get("meta", {}).get("custom_data", {}),
                "raw_payload": webhook_event.payload,
                "timestamp": webhook_event.created_at
            }

            # Route to handler
            await self._route_event(
                webhook_event.event_name,
                webhook_data,
                webhook_event
            )

            await self._mark_processed(webhook_event)

            return {
                "success": True,
                "message": "Event retried successfully",
                "event_id": event_id
            }

        except Exception as e:
            error_message = f"Retry failed: {str(e)}"
            await self._mark_failed(webhook_event, error_message)
            raise WebhookProcessingError(error_message) from e

    async def get_failed_events(
        self,
        limit: int = 100,
        max_retries: int = 3
    ) -> List[WebhookEvent]:
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
            .where(
                WebhookEvent.processed.is_(False),
                WebhookEvent.retry_count < max_retries
            )
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
        processed_stmt = select(func.count(WebhookEvent.id)).where(
            WebhookEvent.processed.is_(True)
        )
        processed_result = await self.db.execute(processed_stmt)
        processed = processed_result.scalar()

        # Failed events
        failed_stmt = select(func.count(WebhookEvent.id)).where(
            WebhookEvent.processed.is_(False)
        )
        failed_result = await self.db.execute(failed_stmt)
        failed = failed_result.scalar()

        # Pending retries (failed with retry_count < 3)
        pending_stmt = select(func.count(WebhookEvent.id)).where(
            WebhookEvent.processed.is_(False),
            WebhookEvent.retry_count < 3
        )
        pending_result = await self.db.execute(pending_stmt)
        pending = pending_result.scalar()

        return {
            "total_events": total or 0,
            "processed_events": processed or 0,
            "failed_events": failed or 0,
            "pending_retries": pending or 0,
            "success_rate": round((processed / total * 100) if total else 0, 2)
        }
