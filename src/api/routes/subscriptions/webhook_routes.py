"""
Payment Webhook endpoints.

Handles webhook events from payment providers (or mock provider in development).
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import Optional, Dict, Any
from uuid import UUID

from src.api.database.async_database import get_async_db
from src.api.models.subscription_models.subscriptions import BillingPeriod
from src.api.models.user_models.users import Users
from src.services.subscription_service import SubscriptionService
from src.services.email_service import EmailService
from src.services.lemonsqueezy_webhook_service import LemonSqueezyWebhookService
from src.services.webhook_handlers import subscription_handlers, order_handlers
from src.services.payment.provider_factory import get_payment_provider_singleton as get_payment_provider
from src.utils.response_utils import success
from src.utils.route_decorators import db_transaction_handler
from src.utils.logger import logger
from sqlalchemy import select


router = APIRouter(
    prefix="/subscriptions/webhooks",
    tags=["subscriptions", "webhooks"]
)


# ============================================================================
# Request Models
# ============================================================================

class MockCheckoutCompleteRequest(BaseModel):
    """Request body for mock checkout completion"""
    session_id: str
    success: bool = True


# ============================================================================
# Webhook Routes
# ============================================================================

@router.post("/mock/checkout-complete", response_model=dict, status_code=status.HTTP_200_OK)
@db_transaction_handler("process mock checkout webhook")
async def handle_mock_checkout_complete(
    request: Request,
    webhook_data: MockCheckoutCompleteRequest,
    db: AsyncSession = Depends(get_async_db)
):
    """
    Handle mock checkout completion webhook.

    This endpoint simulates webhook events from payment providers in development.
    In production, payment providers (e.g., LemonSqueezy) would call their
    respective webhook endpoints.

    Request Body:
    - session_id: Checkout session ID
    - success: Whether checkout was successful

    Returns:
    - Subscription details if successful
    """
    logger.info(f"Received mock checkout webhook for session: {webhook_data.session_id}")

    # Get payment provider
    provider = get_payment_provider()

    # Get checkout session from provider
    # Note: In mock mode, sessions are stored in memory and may be lost on restart
    # For production, sessions would be retrieved from the payment provider's API
    session = provider.checkout_sessions.get(webhook_data.session_id)

    if not session:
        logger.warning(
            f"Checkout session {webhook_data.session_id} not found in provider memory. "
            "This can happen if the backend was restarted. In production, this would "
            "retrieve the session from the payment provider's API."
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Checkout session not found. Please try creating a new checkout session."
        )

    if not webhook_data.success:
        logger.info(f"Checkout cancelled for session: {webhook_data.session_id}")
        return success(
            data={"status": "cancelled"},
            message="Checkout cancelled"
        )

    # Extract metadata from session
    metadata = session.metadata or {}
    user_id = UUID(metadata.get("user_id"))
    plan_id = UUID(metadata.get("plan_id"))
    billing_period_str = metadata.get("billing_period", "monthly")

    # Convert billing period string to enum
    billing_period = BillingPeriod(billing_period_str)

    logger.info(
        f"Creating subscription for user {user_id}, plan {plan_id}, period {billing_period_str}"
    )

    # Create subscription using subscription service
    subscription_service = SubscriptionService(db)

    try:
        # Check if user already has an active subscription
        existing_subscription = await subscription_service.get_subscription_by_user(user_id)
        if existing_subscription:
            logger.warning(f"User {user_id} already has an active subscription")
            return success(
                data={
                    "subscription_id": str(existing_subscription.id),
                    "status": existing_subscription.status.value,
                    "plan_id": str(existing_subscription.plan_id),
                    "billing_period": existing_subscription.billing_period.value
                },
                message="Subscription already exists"
            )

        subscription = await subscription_service.subscribe(
            user_id=user_id,
            plan_id=plan_id,
            billing_period=billing_period
        )

        # Create mock subscription in provider (for consistency)
        # Note: Mock provider doesn't support metadata parameter
        trial_days = 14 if subscription.trial_end_date else None
        provider_subscription = await provider.create_subscription(
            customer_id=session.customer_id,
            price_id=metadata.get("price_id", ""),
            trial_days=trial_days
        )

        # Update subscription with provider subscription ID
        subscription.provider_subscription_id = provider_subscription.subscription_id
        await db.flush()

        logger.info(
            f"Subscription created successfully for user {user_id}: {subscription.id}"
        )

        # Send subscription created email
        try:
            email_service = EmailService(db)

            # Fetch user
            user_result = await db.execute(select(Users).where(Users.id == user_id))
            user = user_result.scalar_one_or_none()

            # Fetch plan details
            plan = await subscription_service.get_plan_by_id(plan_id)

            if user and plan:
                await email_service.send_email(
                    template_type="subscription_created",
                    to_email=user.email,
                    context={
                        "user_name": user.username or user.email.split("@")[0],
                        "plan_name": plan.display_name,
                        "billing_period": billing_period.value,
                        "amount": f"${plan.price_monthly if billing_period == BillingPeriod.MONTHLY else plan.price_yearly}"
                    },
                    user_id=user_id
                )
        except Exception as email_error:
            logger.error(f"Failed to send subscription created email: {str(email_error)}")
            # Don't fail webhook if email fails

        return success(
            data={
                "subscription_id": str(subscription.id),
                "status": subscription.status.value,
                "plan_id": str(subscription.plan_id),
                "billing_period": subscription.billing_period.value
            },
            message="Subscription created successfully"
        )

    except Exception as e:
        logger.error(f"Failed to create subscription: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create subscription: {str(e)}"
        )


@router.post("/lemonsqueezy", status_code=status.HTTP_200_OK)
async def handle_lemonsqueezy_webhook(
    request: Request,
    db: AsyncSession = Depends(get_async_db)
):
    """
    Handle LemonSqueezy webhook events.

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

    Returns:
    - 200 OK if webhook processed successfully
    - 400 Bad Request if signature invalid
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
        # Process webhook
        result = await webhook_service.process_webhook(body, signature)

        logger.info(
            f"LemonSqueezy webhook processed successfully: {result.get('event_type')}",
            extra={"event_id": result.get("event_id")}
        )

        return {"status": "success", "message": "Webhook processed"}

    except ValueError as e:
        # Signature verification failed
        logger.error(f"LemonSqueezy webhook signature verification failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid webhook signature: {str(e)}"
        )
    except Exception as e:
        # Processing failed
        logger.error(f"LemonSqueezy webhook processing failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Webhook processing failed: {str(e)}"
        )
