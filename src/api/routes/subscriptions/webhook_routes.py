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
    In production, real payment providers (Stripe/LemonSqueezy) would call their
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
