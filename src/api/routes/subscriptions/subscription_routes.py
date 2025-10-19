"""
User Subscription API endpoints.

This module provides subscription management operations for end users.
Routes handle HTTP concerns and delegate business logic to SubscriptionService.
"""

from fastapi import APIRouter, Depends, status, Request, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.database.async_database import get_async_db
from src.api.security.dependencies import get_current_user
from src.api.schema.subscription import (
    SubscriptionCreateRequest,
    SubscriptionUpgradeRequest,
    SubscriptionCancelRequest,
    CheckoutSessionRequest,
    CheckoutSessionResponse,
    Invoice,
    InvoiceListResponse
)
from src.api.models.user_models.users import Users
from src.services.subscription_service import SubscriptionService
from src.providers.payment.provider_factory import get_payment_provider_singleton
from src.utils.response_utils import success, created
from src.utils.route_decorators import db_transaction_handler, require_permissions
from sqlalchemy import select


router = APIRouter(
    prefix="/subscriptions",
    tags=["subscriptions"]
)


@router.post("/subscribe", response_model=dict, status_code=status.HTTP_201_CREATED)
@db_transaction_handler("subscribe to plan")
@require_permissions("subscription.manage", workspace_scoped=False)
async def subscribe_to_plan(
    request: Request,
    subscription_data: SubscriptionCreateRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Subscribe to a plan.

    Creates a new subscription for the current user.
    - Free plans: Activated immediately
    - Paid plans: Start with 14-day trial

    Body:
    - plan_id: UUID of the subscription plan
    - billing_period: monthly, yearly, or lifetime

    Returns:
    - Created subscription details
    """
    user_id = current_user.get("identity")
    service = SubscriptionService(db)

    # Create subscription
    new_subscription = await service.subscribe(
        user_id=user_id,
        plan_id=subscription_data.plan_id,
        billing_period=subscription_data.billing_period
    )

    # Get plan name for response
    plan = await service.get_plan_by_id(subscription_data.plan_id)

    # Build response
    response_data = new_subscription.to_dict()
    response_data["plan_name"] = plan.name
    response_data["plan_display_name"] = plan.display_name

    return created(
        data=response_data,
        request=request,
        message=f"Successfully subscribed to {plan.display_name}"
    )


@router.post("/checkout", response_model=dict, status_code=status.HTTP_200_OK)
@db_transaction_handler("create checkout session")
@require_permissions("subscription.manage", workspace_scoped=False)
async def create_checkout_session(
    request: Request,
    checkout_data: CheckoutSessionRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Create LemonSqueezy checkout session for subscription.

    Creates a checkout URL for the user to complete payment.
    The subscription will be created automatically via webhook after successful payment.

    Body:
    - plan_id: UUID of the subscription plan
    - billing_period: monthly or yearly
    - success_url: URL to redirect after successful checkout
    - cancel_url: URL to redirect if checkout is cancelled
    - discount_code: Optional discount/promo code
    - affiliate_code: Optional affiliate/referral code

    Returns:
    - checkout_url: LemonSqueezy checkout URL
    - session_id: Checkout session ID for tracking
    """
    user_id = current_user.get("identity")
    service = SubscriptionService(db)

    # Create checkout session
    checkout_session = await service.create_checkout(
        user_id=user_id,
        plan_id=checkout_data.plan_id,
        billing_period=checkout_data.billing_period,
        success_url=checkout_data.success_url,
        cancel_url=checkout_data.cancel_url,
        discount_code=checkout_data.discount_code,
        affiliate_code=checkout_data.affiliate_code
    )

    return success(
        data=checkout_session,
        request=request,
        message="Checkout session created successfully"
    )


@router.get("/my-subscription", response_model=dict)
@db_transaction_handler("get my subscription", "Subscription retrieved successfully", auto_commit=False)
async def get_my_subscription(
    request: Request,
    include_usage: bool = Query(False, description="Include usage metrics"),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get current user's active subscription.

    Query Parameters:
    - include_usage: If true, include current usage metrics (default: false)

    Returns:
    - Current subscription details with plan information
    - Customer portal URL if subscription exists with LemonSqueezy
    - Usage metrics (if include_usage=true)
    - null if no active subscription
    """
    user_id = current_user.get("identity")
    service = SubscriptionService(db)

    subscription = await service.get_subscription_by_user(user_id)

    if not subscription:
        return success(
            data=None,
            request=request,
            message="No active subscription found"
        )

    # Get plan details
    plan = await service.get_plan_by_id(subscription.plan_id)

    # Build response
    response_data = subscription.to_dict()
    response_data["plan_name"] = plan.name
    response_data["plan_display_name"] = plan.display_name
    response_data["plan_features"] = plan.features
    response_data["plan_limits"] = {
        "max_workspaces": plan.max_workspaces,
        "max_members_per_workspace": plan.max_members_per_workspace,
        "max_topics": plan.max_topics,
        "max_knowledge_items": plan.max_knowledge_items,
        "max_api_calls_per_month": plan.max_api_calls_per_month
    }

    # Add current_period_end as alias for renews_at (frontend compatibility)
    if subscription.renews_at:
        response_data["current_period_end"] = subscription.renews_at.isoformat() if hasattr(subscription.renews_at, 'isoformat') else subscription.renews_at

    # Add customer portal URL if subscription exists with payment provider
    portal_url = await service.get_customer_portal_url(
        user_id=user_id,
        return_url=str(request.url_for("get_my_subscription"))
    )
    response_data["customer_portal_url"] = portal_url

    # Add usage metrics if requested
    if include_usage:
        current_usage = await service.calculate_usage(user_id)
        response_data["current_usage"] = {
            "workspaces": current_usage["workspaces"],
            "topics": current_usage["topics"],
            "knowledge_items": current_usage["knowledge_items"],
            "api_calls": subscription.current_api_calls
        }

    return success(
        data=response_data,
        request=request,
        message="Subscription retrieved successfully"
    )


@router.get("/status", response_model=dict)
@db_transaction_handler("get subscription status", "Subscription status retrieved successfully", auto_commit=False)
async def get_subscription_status(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get subscription status with LemonSqueezy data.

    Lightweight endpoint for quick status checks.
    Returns subscription status, customer portal URL, and basic usage metrics.

    Returns:
    - Subscription status and key information
    - Customer portal URL for subscription management
    - Current usage metrics
    - null if no active subscription
    """
    user_id = current_user.get("identity")
    service = SubscriptionService(db)

    subscription = await service.get_subscription_by_user(user_id)

    if not subscription:
        return success(
            data={
                "has_subscription": False,
                "status": None,
                "customer_portal_url": None
            },
            request=request,
            message="No active subscription found"
        )

    # Get usage metrics
    current_usage = await service.calculate_usage(user_id)

    # Get customer portal URL
    portal_url = await service.get_customer_portal_url(
        user_id=user_id,
        return_url=str(request.url_for("get_subscription_status"))
    )

    # Build lightweight status response
    status_data = {
        "has_subscription": True,
        "subscription_id": str(subscription.id),
        "status": subscription.status.value,
        "billing_period": subscription.billing_period.value,
        "plan_id": str(subscription.plan_id),
        "start_date": subscription.start_date.isoformat() if subscription.start_date else None,
        "end_date": subscription.end_date.isoformat() if subscription.end_date else None,
        "trial_end_date": subscription.trial_end_date.isoformat() if subscription.trial_end_date else None,
        "cancel_at_period_end": subscription.cancel_at_period_end,
        "customer_portal_url": portal_url,
        "lemonsqueezy_subscription_id": subscription.lemonsqueezy_subscription_id,
        "usage": {
            "workspaces": current_usage["workspaces"],
            "topics": current_usage["topics"],
            "knowledge_items": current_usage["knowledge_items"],
            "api_calls": subscription.current_api_calls
        }
    }

    return success(
        data=status_data,
        request=request,
        message="Subscription status retrieved successfully"
    )


@router.get("/history", response_model=dict)
@db_transaction_handler("get subscription history", auto_commit=False)
async def get_subscription_history(
    request: Request,
    limit: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get subscription history for current user.

    Query Parameters:
    - limit: Maximum number of records to return (default: 10, max: 100)

    Returns:
    - List of all subscriptions (past and present) ordered by most recent
    """
    user_id = current_user.get("identity")
    service = SubscriptionService(db)

    # Use service
    subscriptions_data = await service.get_subscription_history(user_id, limit=limit)

    return success(
        data={
            "subscriptions": subscriptions_data,
            "count": len(subscriptions_data)
        },
        request=request,
        message=f"Retrieved {len(subscriptions_data)} subscription(s)"
    )


@router.post("/upgrade", response_model=dict)
@db_transaction_handler("upgrade subscription")
@require_permissions("subscription.manage", workspace_scoped=False)
async def upgrade_subscription(
    request: Request,
    upgrade_data: SubscriptionUpgradeRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Upgrade or downgrade subscription plan.

    Validates that current usage doesn't exceed new plan limits for downgrades.

    Body:
    - new_plan_id: UUID of the new plan
    - billing_period: (optional) Change billing period

    Returns:
    - Updated subscription details
    """
    user_id = current_user.get("identity")
    service = SubscriptionService(db)

    # Upgrade/downgrade subscription
    updated_subscription = await service.upgrade(
        user_id=user_id,
        new_plan_id=upgrade_data.new_plan_id,
        billing_period=upgrade_data.billing_period
    )

    # Get new plan details
    plan = await service.get_plan_by_id(upgrade_data.new_plan_id)

    # Build response
    response_data = updated_subscription.to_dict()
    response_data["plan_name"] = plan.name
    response_data["plan_display_name"] = plan.display_name

    return success(
        data=response_data,
        request=request,
        message=f"Successfully updated to {plan.display_name}"
    )


@router.post("/cancel", response_model=dict)
@db_transaction_handler("cancel subscription")
@require_permissions("subscription.manage", workspace_scoped=False)
async def cancel_subscription(
    request: Request,
    cancel_data: SubscriptionCancelRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Cancel current subscription.

    Body:
    - reason: (optional) Reason for cancellation
    - cancel_immediately: If true, cancel now. If false, cancel at end of billing period.

    Returns:
    - Updated subscription with cancellation details
    """
    user_id = current_user.get("identity")
    service = SubscriptionService(db)

    # Cancel subscription
    subscription = await service.cancel(
        user_id=user_id,
        reason=cancel_data.reason,
        cancel_immediately=cancel_data.cancel_immediately
    )

    message = (
        "Subscription cancelled immediately"
        if cancel_data.cancel_immediately
        else f"Subscription will end on {subscription.end_date.strftime('%Y-%m-%d') if subscription.end_date else 'N/A'}"
    )

    return success(
        data=subscription.to_dict(),
        request=request,
        message=message
    )


@router.get("/usage", response_model=dict)
@db_transaction_handler("get usage stats", "Usage statistics retrieved successfully", auto_commit=False)
async def get_usage_stats(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get current usage statistics vs plan limits.

    Returns:
    - Current resource usage
    - Plan limits
    - Usage percentages
    """
    user_id = current_user.get("identity")
    service = SubscriptionService(db)

    # Get current subscription
    subscription = await service.get_subscription_by_user(user_id)
    if not subscription:
        from src.api.middleware.exceptions import ResourceNotFoundException
        raise ResourceNotFoundException(
            resource_type="Subscription",
            resource_id=f"user:{user_id}",
            message="No active subscription found"
        )

    # Get plan
    plan = await service.get_plan_by_id(subscription.plan_id)

    # Calculate current usage
    current_usage = await service.calculate_usage(user_id)

    # Helper function to calculate percentage
    def calc_percentage(current: int, maximum: int) -> float:
        if maximum == -1:  # Unlimited
            return 0.0
        if maximum == 0:
            return 100.0 if current > 0 else 0.0
        return round((current / maximum) * 100, 1)

    usage_data = {
        "subscription_id": str(subscription.id),
        "plan_name": plan.name if plan else "Unknown",
        "billing_period": subscription.billing_period.value,
        "current_workspaces": current_usage["workspaces"],
        "current_topics": current_usage["topics"],
        "current_knowledge_items": current_usage["knowledge_items"],
        "current_api_calls": subscription.current_api_calls,
        "max_workspaces": plan.max_workspaces if plan else 0,
        "max_topics": plan.max_topics if plan else 0,
        "max_knowledge_items": plan.max_knowledge_items if plan else 0,
        "max_api_calls_per_month": plan.max_api_calls_per_month if plan else 0,
        "workspaces_usage_percent": calc_percentage(current_usage["workspaces"], plan.max_workspaces if plan else 0),
        "topics_usage_percent": calc_percentage(current_usage["topics"], plan.max_topics if plan else 0),
        "knowledge_items_usage_percent": calc_percentage(current_usage["knowledge_items"], plan.max_knowledge_items if plan else 0),
        "api_calls_usage_percent": calc_percentage(subscription.current_api_calls, plan.max_api_calls_per_month if plan else 0),
        "usage_reset_date": subscription.usage_reset_date.isoformat() if subscription.usage_reset_date else None
    }

    return success(
        data=usage_data,
        request=request,
        message="Usage statistics retrieved successfully"
    )


@router.get("/trial-status", response_model=dict)
@db_transaction_handler("get trial status", "Trial status retrieved successfully", auto_commit=False)
async def get_trial_status(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get trial status for current subscription.

    Returns:
    - Whether subscription is in trial
    - Trial end date
    - Days remaining
    - Trial expired status
    """
    user_id = current_user.get("identity")
    service = SubscriptionService(db)

    trial_data = await service.check_trial_status(user_id)

    # Convert datetime to ISO format if present
    if trial_data["trial_end_date"]:
        trial_data["trial_end_date"] = trial_data["trial_end_date"].isoformat()

    return success(
        data=trial_data,
        request=request,
        message="Trial status retrieved successfully"
    )


@router.get("/invoices", response_model=dict)
@db_transaction_handler("get invoices", "Invoices retrieved successfully", auto_commit=False)
async def get_invoices(
    request: Request,
    limit: int = Query(10, ge=1, le=100, description="Maximum number of invoices to return"),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get invoice history for current user.

    Returns list of invoices from LemonSqueezy for the current user's subscription.
    Invoices include payment receipts, billing details, and downloadable PDFs.

    Query Parameters:
    - limit: Maximum number of invoices to return (default: 10, max: 100)

    Returns:
    - invoices: List of invoice objects with details
    - count: Total number of invoices returned

    Each invoice includes:
    - invoice_id: Unique invoice identifier
    - invoice_number: Human-readable invoice number
    - status: paid, unpaid, refunded, etc.
    - amount: Total amount charged
    - invoice_url: Link to view/download invoice PDF
    - invoice_date: Date invoice was created
    - paid_at: Date payment was received
    """
    user_id = current_user.get("identity")

    # Get user to retrieve customer ID
    result = await db.execute(
        select(Users).where(Users.id == user_id)
    )
    user = result.scalar_one_or_none()

    if not user or not user.provider_customer_id:
        # User has no payment provider customer - return empty list
        return success(
            data={
                "invoices": [],
                "count": 0
            },
            request=request,
            message="No invoices found - no payment provider customer"
        )

    # Get payment provider
    payment_provider = get_payment_provider_singleton()

    try:
        # Get invoices from payment provider
        invoices_data = await payment_provider.get_invoices(
            customer_id=user.provider_customer_id,
            limit=limit
        )

        # Format invoices
        invoices = []
        for inv_data in invoices_data:
            invoice = Invoice(
                invoice_id=inv_data.get("invoice_id"),
                invoice_number=inv_data.get("invoice_number"),
                status=inv_data.get("status", "unknown"),
                amount=inv_data.get("amount", 0.0),
                currency=inv_data.get("currency", "USD"),
                tax=inv_data.get("tax"),
                subtotal=inv_data.get("subtotal"),
                invoice_url=inv_data.get("invoice_url"),
                invoice_date=inv_data.get("invoice_date").isoformat() if inv_data.get("invoice_date") else None,
                due_date=inv_data.get("due_date").isoformat() if inv_data.get("due_date") else None,
                paid_at=inv_data.get("paid_at").isoformat() if inv_data.get("paid_at") else None,
                customer_email=inv_data.get("customer_email"),
                customer_name=inv_data.get("customer_name"),
                items=inv_data.get("items", [])
            )
            invoices.append(invoice.dict())

        return success(
            data={
                "invoices": invoices,
                "count": len(invoices)
            },
            request=request,
            message=f"Retrieved {len(invoices)} invoice(s)"
        )

    except Exception as e:
        from src.utils.logger import logger
        logger.error(
            f"Failed to retrieve invoices: {str(e)}",
            extra={"user_id": str(user_id), "error": str(e)}
        )
        # Return empty list on error rather than failing
        return success(
            data={
                "invoices": [],
                "count": 0
            },
            request=request,
            message="Unable to retrieve invoices at this time"
        )
