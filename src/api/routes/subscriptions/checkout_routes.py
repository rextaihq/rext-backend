"""
Checkout and Payment Provider API endpoints.

This module handles checkout sessions, customer portal access, and usage metrics.
It uses the payment provider abstraction to work with any payment provider.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional
from uuid import UUID

from src.api.database.async_database import get_async_db
from src.api.security.dependencies import get_current_user
from src.api.models.user_models.users import Users
from src.api.models.subscription_models.plans import SubscriptionPlan
from src.providers.payment.provider_factory import get_payment_provider_singleton as get_payment_provider
from src.services.usage_tracking_service import UsageTrackingService
from src.config.payment_config import payment_settings
from src.utils.response_utils import success
from src.utils.route_decorators import db_transaction_handler
from src.utils.logger import logger
from src.api.middleware.rate_limiter import customer_portal_rate_limit


router = APIRouter(
    prefix="/subscriptions",
    tags=["subscriptions", "checkout"]
)

# DEBUG: Verify this file is being loaded
print("🔍 DEBUG: checkout_routes.py loaded at", __file__)
print("🔍 DEBUG: create_checkout_session will use 'user' parameter")


# ============================================================================
# Request/Response Models
# ============================================================================

class CheckoutSessionRequest(BaseModel):
    """Request body for creating checkout session"""
    plan_id: UUID
    billing_period: str  # "monthly" or "yearly"


class CheckoutSessionResponse(BaseModel):
    """Response for checkout session creation"""
    session_id: str
    checkout_url: str


class PortalSessionResponse(BaseModel):
    """Response for portal session creation"""
    portal_url: str


# ============================================================================
# Checkout Routes
# ============================================================================

@router.post("/checkout", response_model=dict, status_code=status.HTTP_200_OK)
@db_transaction_handler("create checkout session")
async def create_checkout_session(
    request: Request,
    checkout_request: CheckoutSessionRequest,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Create checkout session with payment provider.

    This endpoint creates a checkout session for subscription purchase.
    The actual checkout is handled by the payment provider (LemonSqueezy or mock provider).

    Request Body:
    - plan_id: UUID of the subscription plan
    - billing_period: "monthly" or "yearly"

    Returns:
    - session_id: Checkout session ID
    - checkout_url: URL to redirect user for checkout
    """
    user_id = user.get("identity")

    # Get provider
    provider = get_payment_provider()

    # Get plan
    plan_query = select(SubscriptionPlan).where(SubscriptionPlan.id == checkout_request.plan_id)
    plan_result = await db.execute(plan_query)
    plan = plan_result.scalar_one_or_none()

    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Subscription plan not found"
        )

    if not plan.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This subscription plan is not available"
        )

    # Get user from database
    user_query = select(Users).where(Users.id == user_id)
    user_result = await db.execute(user_query)
    user_obj = user_result.scalar_one_or_none()

    if not user_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    # Get or create provider customer ID
    if not user_obj.provider_customer_id:
        customer_name = f"{user_obj.first_name} {user_obj.last_name}".strip() or user_obj.display_name or user_obj.email
        customer_id = await provider.create_customer(
            email=user_obj.email,
            name=customer_name,
            metadata={"user_id": str(user_obj.id), "username": user_obj.username}
        )
        user_obj.provider_customer_id = customer_id
        logger.info(f"Created payment provider customer for user {user_obj.email}: {customer_id}")
    else:
        customer_id = user_obj.provider_customer_id

    # Get variant ID based on billing period (LemonSqueezy) or fall back to price ID
    variant_id = None
    if checkout_request.billing_period == "monthly":
        variant_id = plan.lemonsqueezy_variant_id_monthly or plan.provider_price_id_monthly
    elif checkout_request.billing_period == "yearly":
        variant_id = plan.lemonsqueezy_variant_id_yearly or plan.provider_price_id_yearly

    if not variant_id:
        # For mock provider or plans without variant/price IDs configured
        variant_id = f"price_{plan.id}_{checkout_request.billing_period}"
        logger.warning(f"Using generated variant ID for plan {plan.name}: {variant_id}")

    # Create checkout session
    try:
        session = await provider.create_checkout_session(
            customer_id=customer_id,
            price_id=variant_id,  # This is variant_id for LemonSqueezy
            success_url=payment_settings.payment_success_url,
            cancel_url=payment_settings.payment_cancel_url,
            metadata={
                "user_id": str(user_obj.id),
                "plan_id": str(plan.id),
                "billing_period": checkout_request.billing_period
            }
        )

        return success(
            data={
                "session_id": session.session_id,
                "checkout_url": session.checkout_url,
                "plan_name": plan.display_name,
                "billing_period": checkout_request.billing_period
            },
            message="Checkout session created successfully"
        )

    except Exception as e:
        logger.error(f"Failed to create checkout session: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create checkout session: {str(e)}"
        )


@router.get("/portal", response_model=dict, status_code=status.HTTP_200_OK)
@db_transaction_handler("create portal session", auto_commit=False)
async def create_portal_session(
    request: Request,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
    _rate_limit: None = Depends(customer_portal_rate_limit())
):
    """
    Create billing portal session.

    This endpoint creates a session for the customer portal where users can
    manage their subscription, update payment methods, and view invoices.

    Returns:
    - portal_url: URL to redirect user to customer portal
    """
    user_id = user.get("identity")

    # Get user from database
    user_query = select(Users).where(Users.id == user_id)
    user_result = await db.execute(user_query)
    user_obj = user_result.scalar_one_or_none()

    if not user_obj or not user_obj.provider_customer_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No billing account found. Please subscribe to a plan first."
        )

    # Get provider
    provider = get_payment_provider()

    try:
        portal_url = await provider.create_portal_session(
            customer_id=user_obj.provider_customer_id,
            return_url=payment_settings.payment_success_url
        )

        return success(
            data={"portal_url": portal_url},
            message="Portal session created successfully"
        )

    except Exception as e:
        logger.error(f"Failed to create portal session: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create portal session: {str(e)}"
        )


# ============================================================================
# Usage Tracking Routes
# ============================================================================

@router.get("/status", response_model=dict, status_code=status.HTTP_200_OK)
@db_transaction_handler("get subscription status", auto_commit=False)
async def get_subscription_status(
    request: Request,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Get current subscription status with usage metrics.

    Returns complete subscription information including:
    - Current subscription details
    - Plan information
    - Usage metrics for all resource types

    This is the main endpoint for the billing dashboard.
    """
    user_id = user.get("identity")

    # Import here to avoid circular dependency
    from src.services.subscription_service import SubscriptionService

    subscription_service = SubscriptionService(db)
    usage_service = UsageTrackingService(db)

    # Get subscription
    subscription = await subscription_service.get_subscription_by_user(user_id)

    if not subscription:
        # No subscription - return usage with free tier limits
        usage = await usage_service.get_usage_metrics(user_id)
        return success(
            data={
                "subscription": None,
                "plan": None,
                "usage": usage,
                "portal_url": None
            },
            message="No active subscription"
        )

    # Get usage metrics
    usage = await usage_service.get_usage_metrics(user_id)

    # Get user from database to check for customer ID
    user_query = select(Users).where(Users.id == user_id)
    user_result = await db.execute(user_query)
    user_obj = user_result.scalar_one_or_none()

    # Generate customer portal URL if customer exists
    portal_url = None
    if user_obj and user_obj.provider_customer_id:
        try:
            provider = get_payment_provider()
            portal_url = await provider.create_portal_session(
                customer_id=user_obj.provider_customer_id,
                return_url=payment_settings.payment_success_url
            )
        except Exception as e:
            logger.warning(f"Failed to generate portal URL: {str(e)}")
            # Continue without portal URL - not critical

    return success(
        data={
            "subscription": subscription.to_dict(),
            "plan": subscription.plan.to_dict() if subscription.plan else None,
            "usage": usage,
            "portal_url": portal_url
        },
        message="Subscription status retrieved successfully"
    )


@router.get("/usage", response_model=dict, status_code=status.HTTP_200_OK)
@db_transaction_handler("get usage metrics", auto_commit=False)
async def get_usage_metrics(
    request: Request,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Get current usage metrics for the user.

    Returns usage statistics for:
    - Workspaces
    - Members
    - Topics
    - Knowledge items
    - API calls

    Each metric includes used count, limit, and percentage.
    """
    user_id = user.get("identity")
    usage_service = UsageTrackingService(db)

    usage = await usage_service.get_usage_metrics(user_id)

    return success(
        data=usage,
        message="Usage metrics retrieved successfully"
    )


@router.delete("/cancel", response_model=dict, status_code=status.HTTP_200_OK)
@db_transaction_handler("cancel subscription")
async def cancel_subscription(
    request: Request,
    at_period_end: bool = True,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Cancel subscription.

    Query Parameters:
    - at_period_end: If true (default), cancel at end of billing period.
                     If false, cancel immediately.

    Returns:
    - Updated subscription details
    """
    user_id = user.get("identity")

    # Import here to avoid circular dependency
    from src.services.subscription_service import SubscriptionService

    subscription_service = SubscriptionService(db)

    # Cancel subscription
    try:
        subscription = await subscription_service.cancel_subscription(
            user_id=user_id,
            at_period_end=at_period_end
        )

        cancellation_message = (
            "Subscription will be cancelled at the end of the billing period"
            if at_period_end
            else "Subscription cancelled immediately"
        )

        return success(
            data={"subscription": subscription.to_dict()},
            message=cancellation_message
        )

    except Exception as e:
        logger.error(f"Failed to cancel subscription: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to cancel subscription: {str(e)}"
        )
