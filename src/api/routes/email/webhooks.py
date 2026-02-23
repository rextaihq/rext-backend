"""
Resend Webhook Handler

Receives and processes webhook events from Resend email service.
Handles delivery status, opens, clicks, bounces, and spam reports.

Webhook URL (configure in Resend dashboard):
https://your-domain.com/api/v1/email/webhooks/resend

Security:
- Verifies Svix webhook signatures
- Rejects requests with invalid signatures
- Idempotent processing (duplicate events ignored)
"""
from fastapi import APIRouter, Request, HTTPException, Depends, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.database.async_database import get_async_db
from src.services.email_event_service import EmailEventService
from src.api.schema.webhook_schema import WebhookResponse, WebhookProcessingResult
from src.config.email_config import email_config
from src.api.lib.logger import auto_logger

# Import Svix for webhook verification
from svix.webhooks import Webhook, WebhookVerificationError

logger = auto_logger()

router = APIRouter(
    prefix="/webhooks",
    tags=["email-webhooks"]
)


def verify_webhook_signature(
    payload: bytes,
    headers: dict
) -> bool:
    """
    Verify Resend webhook signature using Svix.

    Resend uses Svix for webhook signing, which adds these headers:
    - svix-id: Unique message identifier
    - svix-timestamp: Unix timestamp
    - svix-signature: Cryptographic signature

    Args:
        payload: Raw request body (bytes)
        headers: Request headers

    Returns:
        True if signature is valid

    Raises:
        HTTPException: If signature verification fails
    """
    # Check if webhook secret is configured
    if not email_config.resend_webhook_secret:
        from src.api.config import settings

        if settings.is_production or settings.ENVIRONMENT.lower() == "staging":
            logger.error(
                "CRITICAL: Resend webhook secret not configured in production/staging! "
                "All webhooks will be rejected until RESEND_WEBHOOK_SECRET is set.",
                extra={
                    "environment": settings.ENVIRONMENT,
                    "endpoint": "/api/v1/email/webhooks/resend"
                }
            )
            raise HTTPException(
                status_code=503,
                detail="Webhook verification unavailable — service misconfigured"
            )

        logger.warning(
            "Resend webhook secret not configured - skipping signature verification",
            extra={"warning": "This is insecure for production"}
        )
        # In development, allow webhooks without verification
        # In production, this should be an error
        return True

    # Extract Svix headers
    svix_id = headers.get("svix-id")
    svix_timestamp = headers.get("svix-timestamp")
    svix_signature = headers.get("svix-signature")

    if not all([svix_id, svix_timestamp, svix_signature]):
        logger.error(
            "Missing Svix headers",
            extra={
                "has_id": bool(svix_id),
                "has_timestamp": bool(svix_timestamp),
                "has_signature": bool(svix_signature)
            }
        )
        raise HTTPException(
            status_code=401,
            detail="Missing required webhook signature headers"
        )

    # Verify signature
    try:
        wh = Webhook(email_config.resend_webhook_secret)

        # Reconstruct headers dict for Svix
        svix_headers = {
            "svix-id": svix_id,
            "svix-timestamp": svix_timestamp,
            "svix-signature": svix_signature
        }

        # Verify - this will raise WebhookVerificationError if invalid
        wh.verify(payload, svix_headers)

        logger.debug("Webhook signature verified successfully")
        return True

    except WebhookVerificationError as e:
        logger.error(
            "Webhook signature verification failed",
            extra={
                "error": str(e),
                "svix_id": svix_id
            }
        )
        raise HTTPException(
            status_code=401,
            detail="Invalid webhook signature"
        )
    except Exception as e:
        logger.error(
            f"Webhook verification error: {str(e)}",
            extra={"error_type": type(e).__name__},
            exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail="Error verifying webhook signature"
        )


async def process_webhook_in_background(
    payload: dict,
    db: AsyncSession
):
    """
    Process webhook event in background task.

    Args:
        payload: Webhook payload
        db: Database session
    """
    try:
        service = EmailEventService(db)
        result = await service.process_webhook_event(payload)

        if result.success:
            logger.info(
                "Background webhook processing completed",
                extra={
                    "event_id": result.event_id,
                    "event_type": result.event_type
                }
            )
        else:
            logger.error(
                "Background webhook processing failed",
                extra={
                    "message": result.message,
                    "event_type": result.event_type
                }
            )
    except Exception as e:
        logger.error(
            f"Background webhook processing exception: {str(e)}",
            exc_info=True
        )


@router.post("/resend", response_model=WebhookResponse)
async def handle_resend_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_async_db)
):
    """
    Handle incoming webhooks from Resend.

    This endpoint receives POST requests from Resend when email events occur:
    - email.sent: Email accepted by Resend
    - email.delivered: Email delivered to recipient
    - email.delivery_delayed: Temporary delivery failure
    - email.bounced: Permanent delivery failure
    - email.complained: Recipient marked as spam
    - email.opened: Recipient opened email
    - email.clicked: Recipient clicked link in email

    **Security:**
    - Verifies Svix webhook signatures
    - Rejects unauthorized requests with 401

    **Processing:**
    - Idempotent: Duplicate events are safely ignored
    - Updates email_logs table with delivery status
    - Creates email_events records for tracking
    - Processes asynchronously in background

    **Configuration:**
    Set `RESEND_WEBHOOK_SECRET` in environment variables.
    Get the secret from Resend dashboard when adding webhook endpoint.

    Returns:
        WebhookResponse: Acknowledgement response
    """
    try:
        # Get raw body for signature verification
        body = await request.body()

        # Get headers (case-insensitive)
        headers = {k.lower(): v for k, v in request.headers.items()}

        logger.info(
            "Received webhook from Resend",
            extra={
                "content_length": len(body),
                "has_signature": "svix-signature" in headers
            }
        )

        # Verify webhook signature
        verify_webhook_signature(body, headers)

        # Parse JSON payload
        try:
            import json
            payload = json.loads(body)
        except json.JSONDecodeError as e:
            logger.error(
                f"Invalid JSON in webhook payload: {str(e)}",
                extra={"body_preview": body[:200].decode('utf-8', errors='ignore')}
            )
            raise HTTPException(
                status_code=400,
                detail="Invalid JSON payload"
            )

        # Extract event type for logging
        event_type = payload.get("type", "unknown")
        email_id = payload.get("data", {}).get("email_id", "unknown")

        logger.info(
            "Processing webhook event",
            extra={
                "event_type": event_type,
                "email_id": email_id
            }
        )

        # Process webhook asynchronously in background
        # This allows us to return 200 OK quickly to Resend
        background_tasks.add_task(
            process_webhook_in_background,
            payload,
            db
        )

        # Return success response immediately
        return WebhookResponse(
            status="ok",
            message="Webhook received and queued for processing"
        )

    except HTTPException:
        # Re-raise HTTP exceptions (401, 400, etc.)
        raise

    except Exception as e:
        logger.error(
            f"Unexpected error in webhook handler: {str(e)}",
            extra={"error_type": type(e).__name__},
            exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail="Internal server error processing webhook"
        )


@router.get("/health")
async def webhook_health_check():
    """
    Health check endpoint for webhook service.

    Returns:
        Simple status response
    """
    return {
        "status": "healthy",
        "service": "resend-webhooks",
        "webhook_secret_configured": bool(email_config.resend_webhook_secret)
    }
