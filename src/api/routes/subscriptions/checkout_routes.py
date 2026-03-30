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
from src.services.subscription_service import SubscriptionService
from src.config.payment_config import payment_settings
from src.utils.response_utils import success
from src.utils.route_decorators import db_transaction_handler, require_permissions
from src.utils.logger import logger
from src.api.middleware.rate_limiter import customer_portal_rate_limit, rate_limit
from src.api.schema.response_schemas import SuccessResponse
from src.api.schema.response.checkout_responses import (
    PortalSessionResponse,
    SubscriptionStatusResponse,
    UsageMetricsResponse
)
from src.api.schema.response.subscription_responses import SubscriptionCancelResponse


router = APIRouter(
    prefix="/subscriptions",
    tags=["subscriptions", "checkout"]
)

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
# NOTE: /checkout endpoint is in subscription_routes.py (uses service layer with rate limiting)

@router.get("/portal", response_model=SuccessResponse[PortalSessionResponse], status_code=status.HTTP_200_OK)
@require_permissions("billing.read", workspace_scoped=False)
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
            detail="Failed to create portal session. Please try again or contact support."
        )


# ============================================================================
# Usage Tracking Routes
# ============================================================================

@router.get("/status", response_model=SuccessResponse[SubscriptionStatusResponse], status_code=status.HTTP_200_OK)
@require_permissions("subscription.read", workspace_scoped=False)
@db_transaction_handler("get subscription status", auto_commit=False)
async def get_subscription_status_v2(
    request: Request,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Get current subscription status with usage metrics.

    Required Permission: subscription.read (owner only)
    Scope: User-level (not workspace-scoped)

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


@router.get("/usage", response_model=SuccessResponse[UsageMetricsResponse], status_code=status.HTTP_200_OK)
@require_permissions("usage.read", workspace_scoped=False)
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


@router.post("/cancel", response_model=SuccessResponse[SubscriptionCancelResponse], status_code=status.HTTP_200_OK)
@require_permissions("subscription.manage", workspace_scoped=False)
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
        logger.error("Failed to cancel subscription", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to cancel subscription. Please try again or contact support."
        )
