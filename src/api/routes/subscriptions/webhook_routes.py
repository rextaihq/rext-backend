"""
Payment Webhook endpoints.

Handles webhook events from LemonSqueezy payment provider.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.database.async_database import get_async_db
from src.api.middleware.webhook_security import validate_lemonsqueezy_webhook_ip
from src.services.lemonsqueezy_webhook_service import LemonSqueezyWebhookService
from src.services.webhook_handlers import subscription_handlers, order_handlers
from src.services.webhook_security_monitor import webhook_security_monitor
from src.utils.lemonsqueezy_webhook import WebhookVerificationError
from src.utils.logger import logger
from src.services.audit_logger import audit_logger


router = APIRouter(
    prefix="/subscriptions/webhooks",
    tags=["subscriptions", "webhooks"]
)


@router.post("/lemonsqueezy", status_code=status.HTTP_200_OK)
async def handle_lemonsqueezy_webhook(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    _: None = Depends(validate_lemonsqueezy_webhook_ip)
):
    """
    Handle LemonSqueezy webhook events.

    **Security: Multi-layer webhook protection (Phase 2, Task CRITICAL-4)**

    This endpoint implements defense-in-depth for webhook security:
    1. **Layer 1: IP Whitelist** - Validates request comes from LemonSqueezy IPs
    2. **Layer 2: Signature Verification** - Validates HMAC signature
    3. **Layer 3: Security Monitoring** - Logs all webhook attempts

    This endpoint receives webhook events from LemonSqueezy and processes them
    according to the event type. All events are verified, logged, and routed
    to appropriate handlers.

    Supported Events (12 total):

    Subscription Events (9):
    - subscription_created: New recurring subscription
    - subscription_updated: Subscription plan/status change
    - subscription_cancelled: Subscription cancelled
    - subscription_resumed: Paused subscription resumed
    - subscription_expired: Subscription expired
    - subscription_paused: Subscription paused
    - subscription_payment_success: Payment successful
    - subscription_payment_failed: Payment failed
    - subscription_payment_recovered: Payment recovered after failure

    Order/License Events (3):
    - order_created: One-time purchase (LTD)
    - order_refunded: Order refunded
    - license_key_created: License key generated

    Headers:
    - X-Signature: HMAC signature for webhook verification

    Security Configuration:
    - WEBHOOK_IP_VALIDATION_ENABLED: Enable/disable IP whitelist (default: true)
    - LEMONSQUEEZY_WEBHOOK_IPS: Comma-separated list of allowed IPs/CIDR ranges

    Returns:
    - 200 OK if webhook processed successfully
    - 400 Bad Request if signature invalid
    - 403 Forbidden if IP not in whitelist
    - 500 Internal Server Error if processing fails
    """
    # Get raw body for signature verification
    body = await request.body()

    # Get signature from headers
    signature = request.headers.get("X-Signature", "")

    if not signature:
        logger.warning("LemonSqueezy webhook received without signature")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing webhook signature"
        )

    # Initialize webhook service
    webhook_service = LemonSqueezyWebhookService(db)

    # Register all subscription handlers (9 total)
    webhook_service.register_handler(
        "subscription_created",
        subscription_handlers.handle_subscription_created
    )
    webhook_service.register_handler(
        "subscription_updated",
        subscription_handlers.handle_subscription_updated
    )
    webhook_service.register_handler(
        "subscription_cancelled",
        subscription_handlers.handle_subscription_cancelled
    )
    webhook_service.register_handler(
        "subscription_resumed",
        subscription_handlers.handle_subscription_resumed
    )
    webhook_service.register_handler(
        "subscription_expired",
        subscription_handlers.handle_subscription_expired
    )
    webhook_service.register_handler(
        "subscription_paused",
        subscription_handlers.handle_subscription_paused
    )
    webhook_service.register_handler(
        "subscription_payment_success",
        subscription_handlers.handle_subscription_payment_success
    )
    webhook_service.register_handler(
        "subscription_payment_failed",
        subscription_handlers.handle_subscription_payment_failed
    )
    webhook_service.register_handler(
        "subscription_payment_recovered",
        subscription_handlers.handle_subscription_payment_recovered
    )

    # Register order and license handlers
    webhook_service.register_handler(
        "order_created",
        order_handlers.handle_order_created
    )
    webhook_service.register_handler(
        "order_refunded",
        order_handlers.handle_order_refunded
    )
    webhook_service.register_handler(
        "license_key_created",
        order_handlers.handle_license_key_created
    )

    try:
        # Get client IP for audit logging
        client_ip = request.client.host if request.client else None

        # Process webhook (includes signature verification)
        result = await webhook_service.process_webhook(body, signature)

        logger.info(
            f"LemonSqueezy webhook processed successfully: {result.get('event_type')}",
            extra={"event_id": result.get("event_id")}
        )

        # Audit log - webhook processed successfully
        audit_logger.log_webhook_processed(
            event_id=result.get("event_id", "unknown"),
            event_name=result.get("event_type", "unknown"),
            processing_time_ms=result.get("processing_time_ms", 0),
            metadata={"status": "success"},
        )

        return {"status": "success", "message": "Webhook processed"}

    except WebhookVerificationError as e:
        # Signature verification failed - Record security event
        client_ip = request.client.host if request.client else "unknown"

        # Try to extract event type from payload (for logging)
        event_type = None
        try:
            import json
            payload_data = json.loads(body)
            event_type = payload_data.get("meta", {}).get("event_name")
        except:
            pass

        # Record failure in security monitor
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
                "signature_prefix": signature[:8] if len(signature) >= 8 else signature
            }
        )

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook signature"
        )
    except Exception as e:
        # Processing failed
        logger.error(f"LemonSqueezy webhook processing failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Webhook processing failed: {str(e)}"
        )
