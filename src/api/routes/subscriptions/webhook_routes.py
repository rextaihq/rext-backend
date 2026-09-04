"""
Payment Webhook endpoints.

Handles webhook events from LemonSqueezy payment provider.
Validates signature synchronously, then processes in background.
"""

import json
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status, Request
from pydantic import BaseModel
from src.api.database.async_database import AsyncSessionLocal
from src.api.middleware.webhook_security import validate_lemonsqueezy_webhook_ip
from src.services.lemonsqueezy_webhook_service import LemonSqueezyWebhookService
from src.services.webhook_handlers import subscription_handlers, order_handlers, register_default_handlers
from src.services.webhook_security_monitor import webhook_security_monitor
from src.utils.lemonsqueezy_webhook import verify_webhook_signature, WebhookVerificationError
from src.utils.logger import logger
from src.services.audit_logger import audit_logger


router = APIRouter(
    prefix="/subscriptions/webhooks",
    tags=["subscriptions", "webhooks"]
)


def _register_all_handlers(webhook_service: LemonSqueezyWebhookService) -> None:
    """Register all subscription, order, and license handlers.

    Thin wrapper kept for backwards compatibility - the canonical registry now
    lives in ``src.services.webhook_handlers.register_default_handlers``.
    """
    register_default_handlers(webhook_service)


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
            
            # Commit changes BEFORE sending emails
            await db.commit()

            logger.info(
                f"LemonSqueezy webhook processed in background: {result.get('event_type')}",
                extra={"event_id": result.get("event_id")}
            )

            # Handle post-commit tasks (like sending emails)
            handler_result = result.get("handler_result")
            if handler_result and isinstance(handler_result, dict) and handler_result.get("send_email"):
                try:
                    await _send_webhook_email(handler_result, db)
                except Exception as email_err:
                    logger.error(f"Failed to send post-webhook email: {email_err}")

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

            # Emit a failure audit event to mirror the success path
            # (log_webhook_processed). The webhook_events row already carries the
            # error via LemonSqueezyWebhookService._mark_failed; this makes the
            # failure visible in the audit stream too.
            event_id = "unknown"
            event_name = "unknown"
            try:
                _payload = json.loads(body)
                _meta = _payload.get("meta", {}) or {}
                event_id = _meta.get("event_id") or _payload.get("id") or "unknown"
                event_name = _meta.get("event_name", "unknown")
            except Exception:
                pass

            try:
                audit_logger.log_webhook_failed(
                    event_id=str(event_id),
                    event_name=str(event_name),
                    error=str(e),
                )
            except Exception:
                logger.warning("Failed to emit webhook_failed audit event", exc_info=True)


async def _send_webhook_email(task_data: dict, db: AsyncSessionLocal) -> None:
    """Send email based on task data from webhook handler."""
    from src.services.billing_email_service import BillingEmailService
    
    email_type = task_data.get("email_type")
    data = task_data.get("email_data", {})
    user_id = data.get("user_id")
    
    if not email_type or not user_id:
        return

    # Use a new session for email sending to ensure it's independent
    async with AsyncSessionLocal() as email_db:
        billing_email = BillingEmailService(email_db)
        
        if email_type == "payment_failed":
            await billing_email.send_payment_failed_email(
                user_id=user_id,
                plan_name=data.get("plan_name"),
                amount=f"${data.get('amount_cents', 0) / 100:.2f}",
                retry_date=data.get("retry_date")
            )
        elif email_type == "payment_recovered":
            await billing_email.send_payment_recovered_email(
                user_id=user_id,
                plan_name=data.get("plan_name"),
                amount=f"${data.get('amount_cents', 0) / 100:.2f}",
                recovery_date=data.get("recovery_date"),
                next_billing_date=data.get("next_billing_date")
            )
        elif email_type == "subscription_created":
            await billing_email.send_subscription_created_email(
                user_id=user_id,
                plan_name=data.get("plan_name"),
                plan_price=data.get("plan_price"),
                billing_period=data.get("billing_period"),
                features=data.get("features", [])
            )
        elif email_type == "payment_succeeded":
            await billing_email.send_payment_succeeded_email(
                user_id=user_id,
                plan_name=data.get("plan_name"),
                amount=f"${data.get('amount_cents', 0) / 100:.2f}",
                payment_date=data.get("payment_date"),
                next_billing_date=data.get("next_billing_date")
            )
        elif email_type == "subscription_cancelled":
            await billing_email.send_subscription_cancelled_email(
                user_id=user_id,
                plan_name=data.get("plan_name"),
                end_date=data.get("end_date")
            )
        # Add other types as needed


@router.post("/lemonsqueezy", status_code=status.HTTP_200_OK)
# NOTE: Not migrated — acts as a webhook receiver (LemonSqueezy)
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
    from src.config.payment_config import payment_settings
    is_valid = verify_webhook_signature(
        payload=body,
        signature=signature,
        secret=payment_settings.lemonsqueezy_webhook_secret
    )

    if not is_valid:
        client_ip = request.client.host if request.client else "unknown"

        # Try to extract event info for logging
        event_type = None
        event_id = "unknown"
        try:
            payload_data = json.loads(body)
            _meta = payload_data.get("meta", {}) or {}
            event_type = _meta.get("event_name")
            event_id = _meta.get("event_id") or payload_data.get("id") or "unknown"
        except Exception:
            pass

        try:
            audit_logger.log_webhook_received(
                event_id=str(event_id),
                event_name=str(event_type or "unknown"),
                signature_valid=False,
                ip_address=client_ip,
            )
        except Exception:
            logger.warning("Failed to emit webhook_received audit event", exc_info=True)

        # Record failure in security monitor
        await webhook_security_monitor.record_verification_failure(
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

    # Signature valid — record receipt, acknowledge immediately, process in background
    try:
        _payload = json.loads(body)
        _meta = _payload.get("meta", {}) or {}
        audit_logger.log_webhook_received(
            event_id=str(_meta.get("event_id") or _payload.get("id") or "unknown"),
            event_name=str(_meta.get("event_name") or "unknown"),
            signature_valid=True,
            ip_address=request.client.host if request.client else None,
        )
    except Exception:
        logger.warning("Failed to emit webhook_received audit event", exc_info=True)

    background_tasks.add_task(_process_webhook_in_background, body, signature)

    return {"status": "accepted", "message": "Webhook received, processing in background"}
