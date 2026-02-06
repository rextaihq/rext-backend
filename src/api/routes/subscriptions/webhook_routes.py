"""
Payment Webhook endpoints.

Handles webhook events from LemonSqueezy payment provider.
Validates signature synchronously, then processes in background.
"""

import json
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status, Request
from src.api.config import get_settings
from src.api.database.async_database import AsyncSessionLocal
from src.api.middleware.webhook_security import validate_lemonsqueezy_webhook_ip
from src.services.lemonsqueezy_webhook_service import LemonSqueezyWebhookService
from src.services.webhook_handlers import subscription_handlers, order_handlers
from src.services.webhook_security_monitor import webhook_security_monitor
from src.utils.lemonsqueezy_webhook import verify_webhook_signature, WebhookVerificationError
from src.utils.logger import logger
from src.services.audit_logger import audit_logger


router = APIRouter(
    prefix="/subscriptions/webhooks",
    tags=["subscriptions", "webhooks"]
)


def _register_all_handlers(webhook_service: LemonSqueezyWebhookService) -> None:
    """Register all subscription, order, and license handlers."""
    # Subscription handlers (9)
    webhook_service.register_handler("subscription_created", subscription_handlers.handle_subscription_created)
    webhook_service.register_handler("subscription_updated", subscription_handlers.handle_subscription_updated)
    webhook_service.register_handler("subscription_cancelled", subscription_handlers.handle_subscription_cancelled)
    webhook_service.register_handler("subscription_resumed", subscription_handlers.handle_subscription_resumed)
    webhook_service.register_handler("subscription_expired", subscription_handlers.handle_subscription_expired)
    webhook_service.register_handler("subscription_paused", subscription_handlers.handle_subscription_paused)
    webhook_service.register_handler("subscription_payment_success", subscription_handlers.handle_subscription_payment_success)
    webhook_service.register_handler("subscription_payment_failed", subscription_handlers.handle_subscription_payment_failed)
    webhook_service.register_handler("subscription_payment_recovered", subscription_handlers.handle_subscription_payment_recovered)

    # Order and license handlers (3)
    webhook_service.register_handler("order_created", order_handlers.handle_order_created)
    webhook_service.register_handler("order_refunded", order_handlers.handle_order_refunded)
    webhook_service.register_handler("license_key_created", order_handlers.handle_license_key_created)


async def _process_webhook_in_background(body: bytes, signature: str) -> None:
    """
    Process webhook event in a background task with its own DB session.

    This runs after the 200 response has been sent to LemonSqueezy,
    preventing timeout-induced retries.
    """
    async with AsyncSessionLocal() as db:
        try:
            webhook_service = LemonSqueezyWebhookService(db)
            _register_all_handlers(webhook_service)

            result = await webhook_service.process_webhook(body, signature)
            await db.commit()

            logger.info(
                f"LemonSqueezy webhook processed in background: {result.get('event_type')}",
                extra={"event_id": result.get("event_id")}
            )

            audit_logger.log_webhook_processed(
                event_id=result.get("event_id", "unknown"),
                event_name=result.get("event_type", "unknown"),
                processing_time_ms=result.get("processing_time_ms", 0),
                metadata={"status": "success"},
            )

        except Exception as e:
            await db.rollback()
            logger.error(
                f"LemonSqueezy webhook background processing failed: {str(e)}",
                exc_info=True
            )


@router.post("/lemonsqueezy", status_code=status.HTTP_200_OK)
async def handle_lemonsqueezy_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    _: None = Depends(validate_lemonsqueezy_webhook_ip)
):
    """
    Handle LemonSqueezy webhook events.

    **Security: Multi-layer webhook protection**

    1. **Layer 1: IP Whitelist** - Validates request comes from LemonSqueezy IPs
    2. **Layer 2: Signature Verification** - Validates HMAC signature (before 200 response)
    3. **Layer 3: Background Processing** - Event processed asynchronously after acknowledgment

    Returns 200 immediately after signature validation to prevent LemonSqueezy
    timeout retries. Actual processing happens in a background task.

    Returns:
    - 200 OK if signature is valid (processing continues in background)
    - 400 Bad Request if signature missing
    - 401 Unauthorized if signature invalid
    - 403 Forbidden if IP not in whitelist
    """
    # Get raw body and signature
    body = await request.body()
    signature = request.headers.get("X-Signature", "")

    logger.info(
        f"Received LemonSqueezy webhook: {len(body)} bytes",
        extra={"has_signature": bool(signature)}
    )

    if not signature:
        logger.warning("LemonSqueezy webhook received without signature")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing webhook signature"
        )

    # Verify signature synchronously before returning 200
    settings = get_settings()
    is_valid = verify_webhook_signature(
        payload=body,
        signature=signature,
        secret=settings.LEMONSQUEEZY_WEBHOOK_SECRET
    )

    if not is_valid:
        client_ip = request.client.host if request.client else "unknown"

        # Try to extract event type for logging
        event_type = None
        try:
            payload_data = json.loads(body)
            event_type = payload_data.get("meta", {}).get("event_name")
        except Exception:
            pass

        webhook_security_monitor.record_verification_failure(
            ip_address=client_ip,
            event_type=event_type,
            signature_prefix=signature[:8] if len(signature) >= 8 else signature,
            payload_size=len(body)
        )

        logger.error(
            f"LemonSqueezy webhook signature verification failed from {client_ip}",
            extra={
                "event": "webhook_verification_failed",
                "ip_address": client_ip,
                "event_type": event_type,
            }
        )

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook signature"
        )

    # Signature valid — acknowledge immediately, process in background
    background_tasks.add_task(_process_webhook_in_background, body, signature)

    return {"status": "accepted", "message": "Webhook received, processing in background"}
