"""
User Subscription API endpoints.

This module provides subscription management operations for end users.
Routes handle HTTP concerns and delegate business logic to SubscriptionService.
"""

from typing import Optional

from fastapi import APIRouter, Depends, status, Request, Query, BackgroundTasks
from src.api.routes.subscriptions.plan_routes import get_plan
from src.services.billing_email_service import (
    BillingEmailService,
    send_billing_email_in_background,
)
from src.services.notification_helper import schedule_if_allowed
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.database.async_database import get_async_db
from src.api.security.dependencies import get_current_user
from src.api.schema.subscription import (
    SubscriptionCreateRequest,
    SubscriptionUpgradeRequest,
    SubscriptionCancelRequest,
    CheckoutSessionRequest,
    Invoice,
)
from src.api.models.user_models.users import Users
from src.api.models.subscription_models.licenses import License
from src.api.models.subscription_models.subscriptions import UserSubscription
from datetime import datetime, timedelta, timezone
from src.api.models.subscription_models.orders import Order, OrderStatus
from src.api.models.subscription_models.refunds import Refund, RefundStatus
from src.api.models.subscription_models.refund_requests import (
    REFUND_REQUEST_WINDOW_DAYS,
    RefundRequest,
    RefundRequestStatus,
)
from src.services.order_service import order_to_invoice_dict, refundable_amount
from src.services.refund_service import RefundService
from src.services.subscription_service import SubscriptionService
from src.services.subscription_plan_service import SubscriptionPlanService
from src.providers.payment.provider_factory import get_payment_provider_singleton
from src.utils.response_utils import created, success, not_found, error
from src.utils.route_decorators import db_transaction_handler
from src.config.payment_config import payment_settings
from src.api.config import get_settings
from src.api.schema.subscription.enums import BillingPeriod
from src.api.schema.response_schemas import SuccessResponse
from src.api.schema.response.subscription_responses import (
    SubscriptionDetails,
    SubscriptionHistoryResponse,
    SubscriptionUpgradeResponse,
    SubscriptionCancelResponse,
    InvoiceListResponse,
    OrderListResponse,
    BillingUrlsResponse
)
from src.api.schema.response.refund_responses import (
    RefundRequestRow,
    RefundRequestListResponse,
)
from src.api.schema.subscription.refund_schemas import RefundRequestCreate
from src.services.refund_request_service import (
    RefundRequestError,
    RefundRequestService,
)
from src.api.schema.response.checkout_responses import (
    CheckoutSessionResponse,
    PortalSessionResponse,
    SubscriptionStatusResponse,
    UsageMetricsResponse
)
from src.api.schema.response.trial_responses import TrialStatusResponse
from src.api.middleware.rate_limiter import (
    checkout_rate_limit,
    subscription_update_rate_limit,
    subscription_cancel_rate_limit,
    customer_portal_rate_limit
)
from src.services.usage_tracking_service import UsageTrackingService
from sqlalchemy import select
from src.utils.logger import logger

from fastapi import HTTPException, BackgroundTasks
from src.api.middleware.exceptions import ResourceNotFoundException

settings = get_settings()

router = APIRouter(
    prefix="/subscriptions",
    tags=["subscriptions"]
)


async def _send_cancellation_email(user_id: str, plan_name: str, end_date: str) -> None:
    """
    Send the subscription-cancelled email using a fresh DB session.

    Runs as a FastAPI background task (after the response is sent, so after
    the request's own transaction has already committed the cancellation).
    """
    from src.api.database.async_database import AsyncSessionLocal
    from src.services.billing_email_service import BillingEmailService

    async with AsyncSessionLocal() as email_db:
        try:
            billing_email = BillingEmailService(email_db)
            await billing_email.send_subscription_cancelled_email(
                user_id=user_id,
                plan_name=plan_name,
                end_date=end_date,
            )
        except Exception as exc:
            logger.error(f"Failed to send subscription cancellation email for user {user_id}: {exc}")


@router.post("/subscribe", response_model=SuccessResponse[SubscriptionDetails], status_code=status.HTTP_201_CREATED)
@db_transaction_handler("subscribe to plan")
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

    return success(
        data=response_data,
        request=request,
        message="Subscribed to plan successfully"
    )



@router.post("/checkout", response_model=SuccessResponse[CheckoutSessionResponse], status_code=status.HTTP_200_OK)
@db_transaction_handler("create checkout session")
async def create_checkout_session(
    request: Request,
    checkout_data: CheckoutSessionRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
    _rate_limit: None = Depends(checkout_rate_limit())
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
    logger.info(f"Creating checkout session for user {user_id}")

    # Create checkout session
    checkout_session = await service.create_checkout(
        user_id=user_id,
        plan_id=checkout_data.plan_id,
        billing_period=checkout_data.billing_period,
        success_url=checkout_data.success_url,
        cancel_url=checkout_data.cancel_url,
        affiliate_code=checkout_data.affiliate_code
    )

    logger.info(f"Checkout session created for user {user_id}")
    return success(
        data=checkout_session,
        request=request,
        message="Checkout session created successfully"
    )


@router.get("/credits", status_code=status.HTTP_200_OK)
@db_transaction_handler("get credit balance", auto_commit=False)
async def get_credit_balance(
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Return current credit balance for the authenticated user."""
    from sqlalchemy.orm import selectinload
    from src.api.models.subscription_models.subscriptions import UserSubscription, subscription_grants_access
    from sqlalchemy import select as sa_select, and_

    user_id = current_user.get("identity")
    result = await db.execute(
        sa_select(UserSubscription).options(
            selectinload(UserSubscription.plan)
        ).where(
            and_(
                UserSubscription.user_id == user_id,
                subscription_grants_access(),
            )
        ).order_by(UserSubscription.start_date.desc()).limit(1)
    )
    subscription = result.scalar_one_or_none()

    if not subscription:
        return success(
            data={
                "current_credits": 0,
                "credits_per_month": None,
                "credits_reset_date": None,
                "articles_remaining": 0,
                "plan_name": None,
            },
            message="No active subscription.",
        )

    plan = subscription.plan
    credits = subscription.current_credits or 0
    monthly = plan.credits_per_month if plan else None
    unlimited = monthly is None

    return success(
        data={
            "current_credits": credits,
            "credits_per_month": monthly,
            "credits_reset_date": subscription.credits_reset_date.isoformat() if subscription.credits_reset_date is not None else None,
            "articles_remaining": None if unlimited else max(0, credits // 15),
            "plan_name": plan.display_name if plan else None,
        },
        message="Credit balance retrieved.",
    )


@router.get("/my-subscription", response_model=SuccessResponse[SubscriptionDetails])
@router.get("/current", response_model=SuccessResponse[SubscriptionDetails])  # Alias for compatibility
@db_transaction_handler("get my subscription", "Subscription retrieved successfully", auto_commit=False)
async def get_my_subscription(
    background_tasks: BackgroundTasks,
    request: Request,
    include_usage: bool = Query(False, description="Include usage metrics"),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
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

    # Kept outside `subscription` so it survives a refund or cancellation:
    # access goes away, the saved card stays on the billing screen.
    billing_account = await service.get_billing_account(user_id)

    if not subscription:
        return success(
            data={"subscription": None, "billing_account": billing_account},
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

    # Add payment card details if available
    meta = subscription.subscription_metadata or {}
    response_data["card_brand"] = meta.get("card_brand")
    response_data["card_last_four"] = meta.get("card_last_four") or meta.get("card_last4")

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

    # Add available plans for discovery
    plan_service = SubscriptionPlanService(db)
    available_plans = await plan_service.list_plans(include_inactive=False, include_private=False, is_admin=False)
    response_data["plans"] = available_plans.get("plans", [])

    # Add user licenses
    license_result = await db.execute(
        select(License).where(License.user_id == user_id)
    )
    licenses = license_result.scalars().all()
    response_data["licenses"] = [l.to_dict() for l in licenses]
    response_data["activations_count"] = sum(l.activation_count for l in licenses)

    # Schedule expiring notification if renewal is near (within 3 days)
    if subscription.renews_at:
        from datetime import datetime, timezone, timedelta
        
        # Ensure renews_at is timezone-aware for comparison
        renews_at = subscription.renews_at
        if renews_at.tzinfo is None:
            renews_at = renews_at.replace(tzinfo=timezone.utc)
            
        now = datetime.now(timezone.utc)
        if 0 <= (renews_at - now).days <= 3:
            await schedule_if_allowed(

                db=db,
                user_id=str(user_id),
                background_tasks=background_tasks,
                pref_flag="subscription_expiring",
                message="Your subscription is about to expire.",
                payload={"subscription_id": str(subscription.id), "renewal_date": subscription.renews_at.isoformat()},
            )
    return success(
        data={"subscription": response_data, "billing_account": billing_account},
        request=request,
        message="Subscription retrieved successfully"
    )


# NOTE: /status endpoint is in checkout_routes.py (includes portal URL and free tier usage)

@router.get("/history", response_model=SuccessResponse[SubscriptionHistoryResponse])
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


@router.post("/upgrade", response_model=SuccessResponse[SubscriptionUpgradeResponse])
@db_transaction_handler("upgrade subscription")
async def upgrade_subscription(
    request: Request,
    upgrade_data: SubscriptionUpgradeRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
    _rate_limit: None = Depends(subscription_update_rate_limit())
):
    """
    Upgrade a subscription plan.

    Validates the new plan ID and ensures subscription upgrade.

    Body:
    - new_plan_id: UUID of the new plan (required)
    - billing_period: optional, monthly/yearly/lifetime

    Returns:
    - Updated subscription details
    """
    user_id = current_user.get("identity")
    service = SubscriptionService(db)

    # Validate new_plan_id
    if not upgrade_data.new_plan_id:
        raise HTTPException(
            status_code=400,
            detail="new_plan_id is required and must be a valid UUID"
        )

    # Fetch the new plan
    new_plan = await service.get_plan_by_id(upgrade_data.new_plan_id)
    if not new_plan:
        raise HTTPException(
            status_code=404,
            detail="The specified plan does not exist"
        )

    # Fetch current subscription
    current_subscription = await service.get_subscription_by_user(user_id)
    if not current_subscription:
        raise HTTPException(
            status_code=404,
            detail="Current subscription not found"
        )

    # Prevent upgrade to lower plan accidentally
    current_plan_price = float(current_subscription.plan.price_monthly or 0) if current_subscription.plan else 0
    new_plan_price = float(new_plan.price_monthly or 0)
    if new_plan_price < current_plan_price:
        raise HTTPException(
            status_code=400,
            detail="Cannot upgrade to a lower-priced plan. Use downgrade endpoint instead."
        )

    # Trial → paid: trial plan is local-only (no LemonSqueezy subscription), must go through checkout
    current_plan_name = current_subscription.plan.name.lower() if current_subscription.plan else ""
    is_trial = current_plan_name == "trial"
    if is_trial and new_plan_price > 0:
        billing_period = upgrade_data.billing_period or BillingPeriod.MONTHLY
        checkout_session = await service.create_checkout(
            user_id=user_id,
            plan_id=upgrade_data.new_plan_id,
            billing_period=billing_period,
            # LemonSqueezy uses redirect_url for the confirmation modal's
            # "Continue" button. It must land on /checkout/success: this
            # subscription row is only written by the async webhook, so the
            # frontend needs that page's bounded polling to wait for it.
            # Landing on the root dashboard instead shows the pre-upgrade plan
            # until the user manually reloads.
            success_url=payment_settings.payment_success_url,
            cancel_url=payment_settings.payment_cancel_url,
            skip_subscription_check=True,
        )
        return success(
            data={
                "action": "checkout_required",
                "checkout_url": checkout_session["checkout_url"],
                "session_id": checkout_session["session_id"],
                "plan_name": new_plan.name,
                "plan_display_name": new_plan.display_name,
            },
            request=request,
            message="Payment required to upgrade. Redirect user to checkout_url."
        )

    # Paid → paid: provider handles proration billing automatically
    updated_subscription = await service.upgrade(
        user_id=user_id,
        new_plan_id=upgrade_data.new_plan_id,
        billing_period=upgrade_data.billing_period
    )

    response_data = updated_subscription.to_dict()
    response_data["plan_name"] = new_plan.name
    response_data["plan_display_name"] = new_plan.display_name

    return success(
        data=response_data,
        request=request,
        message=f"Successfully upgraded to {new_plan.display_name}"
    )

    
#downgrade route
@router.post("/downgrade", response_model=SuccessResponse[SubscriptionUpgradeResponse])
@db_transaction_handler("downgrade subscription")
async def downgrade_subscription(
    request: Request,
    downgrade_data: SubscriptionUpgradeRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
    _rate_limit: None = Depends(subscription_update_rate_limit())
):
    """
    Downgrade subscription plan.

    Validates that current usage doesn't exceed new plan limits.

    Body:
    - new_plan_id: UUID of the lower plan
    - billing_period: (optional) Change billing period

    Returns:
    - Updated subscription details
    """
    user_id = current_user.get("identity")
    service = SubscriptionService(db)
    
    #  Validate plan id
    if not downgrade_data.new_plan_id:
        raise HTTPException(
            status_code=400,
            detail="plan id is required"
        )
    # Fetch current subscription and plan
    subscription = await service.get_subscription_by_user(user_id)
    if not subscription:
        raise HTTPException(
            status_code=404,
            detail="No active subscription found"
        )
    current_plan = await service._get_plan_or_404(subscription.plan_id)

    # Fetch new plan
    new_plan = await service.get_plan_by_id(downgrade_data.new_plan_id)

    # Prevent downgrade to higher plan
    current_plan_price = float(current_plan.price_monthly or 0)
    new_plan_price = float(new_plan.price_monthly or 0)
    if new_plan_price > current_plan_price:
        raise HTTPException(
            status_code=400,
            detail="Use upgrade subscription to move to the higher plan"
        )
 
    
    # Downgrade subscription (same logic as upgrade)
    updated_subscription = await service.upgrade(
        user_id=user_id,
        new_plan_id=downgrade_data.new_plan_id,
        billing_period=downgrade_data.billing_period
    )

    # Build response
    response_data = updated_subscription.to_dict()
    response_data["plan_name"] = new_plan.name
    response_data["plan_display_name"] = new_plan.display_name

    return success(
        data=response_data,
        request=request,
        message=f"Successfully downgraded to {new_plan.display_name}"
    )

@router.post("/cancel", response_model=SuccessResponse[SubscriptionCancelResponse])
@db_transaction_handler("cancel subscription")
async def cancel_subscription(
    request: Request,
    cancel_data: SubscriptionCancelRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
    _rate_limit: None = Depends(subscription_cancel_rate_limit())
):
    """
    Cancel a subscription.

    Cancels the user's active subscription either immediately or at the end
    of the billing period, depending on cancel_immediately flag.

    Body:
    - reason: Cancellation reason (optional)
    - cancel_immediately: If true, cancel now; if false, cancel at period end

    Returns:
    - HTTP 200: Subscription cancelled successfully
    - HTTP 404: No active subscription found
    - HTTP 500: Server error (handled by decorator)
    """
    user_id = current_user.get("identity")
    service = SubscriptionService(db)

    # Cancel subscription
    subscription = await service.cancel(
        user_id=user_id,
        reason=cancel_data.reason,
        cancel_immediately=cancel_data.cancel_immediately,
        background_tasks=background_tasks
    )

    if not subscription:
        raise ResourceNotFoundException(
            resource_type="subscription",
            message="No active subscription found to cancel"
        )

    message = (
        "Subscription cancelled immediately"
        if cancel_data.cancel_immediately
        else f"Subscription will end on {subscription.end_date.strftime('%Y-%m-%d') if subscription.end_date else 'N/A'}"
    )

    # Schedule cancellation notification
    await schedule_if_allowed(
        db=db,
        user_id=str(user_id),
        background_tasks=background_tasks,
        pref_flag="billing_subscription_cancelled",
        message="Your subscription has been cancelled.",
        payload={"subscription_id": str(subscription.id), "type": "cancelled"},
    )

    # Send cancellation email here only when there's no payment-provider
    # subscription to drive it - if there is one, LemonSqueezy's own
    # subscription_cancelled webhook fires shortly after and sends it there
    # instead (avoids sending the email twice for the common paid-plan case).
    if not (subscription.provider_subscription_id or subscription.lemonsqueezy_subscription_id):
        background_tasks.add_task(
            _send_cancellation_email,
            user_id=str(user_id),
            plan_name=subscription.plan.name if subscription.plan else "Your Plan",
            end_date=subscription.end_date.strftime("%B %d, %Y") if subscription.end_date else "the end of your billing period",
        )

    # Return raw data - decorator handles success response formatting
    return success(
        data=subscription.to_dict(),
        request=request,
        message=message
    )

@router.get("/usage", response_model=SuccessResponse[UsageMetricsResponse])
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
    usage_service = UsageTrackingService(db)

    usage_data = await usage_service.get_usage_metrics(user_id)

    return success(
        data=usage_data,
        request=request,
        message="Usage statistics retrieved successfully"
    )


@router.get("/trial-status", response_model=SuccessResponse[TrialStatusResponse])
@db_transaction_handler("get trial status", "Trial status retrieved successfully", auto_commit=False)
async def get_trial_status(
    background_tasks: BackgroundTasks,
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
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

    # Schedule trial ending notification if trial ends within 3 days
    if trial_data.get("trial_end_date"):
        from datetime import datetime, timezone, timedelta
        trial_end = datetime.fromisoformat(trial_data["trial_end_date"]).replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        if 0 <= (trial_end - now).days <= 3:
            await schedule_if_allowed(
                db=db,
                user_id=str(user_id),
                background_tasks=background_tasks,
                pref_flag="trial_ending",
                message="Your trial period is ending soon.",
                payload={"trial_end_date": trial_data["trial_end_date"]},
            )
    return success(
        data=trial_data,
        request=request,
        message="Trial status retrieved successfully"
    )


@router.get("/orders", response_model=SuccessResponse[OrderListResponse])
@db_transaction_handler("get orders", "Orders retrieved successfully", auto_commit=False)
async def get_orders(
    request: Request,
    limit: int = Query(50, ge=1, le=100, description="Maximum number of orders to return"),
    offset: int = Query(0, ge=0, description="Number of orders to skip"),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get purchase history for the current user.

    Reads our own orders table rather than calling LemonSqueezy, so the billing
    page does not depend on their API being up or within rate limits. The table
    is kept current by the order webhooks.

    Query Parameters:
    - limit: Maximum number of orders to return (default: 50, max: 100)
    - offset: Number of orders to skip, for pagination

    Returns:
    - orders: Purchases newest first, each with its LemonSqueezy receipt URL
    - count: Number of orders returned
    """
    user_id = current_user.get("identity")

    result = await db.execute(
        select(Order)
        .where(Order.user_id == user_id)
        # Fall back to created_at: ordered_at is null for rows recorded before
        # the order timestamp was captured.
        .order_by(Order.ordered_at.desc().nullslast(), Order.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    orders = result.scalars().all()

    # Latest request per order, so each row can show its own state. One query
    # for the page rather than one per row.
    requests_by_order = {}
    all_requests = []
    if orders:
        request_rows = await db.execute(
            select(RefundRequest)
            .where(RefundRequest.order_id.in_([o.id for o in orders]))
            .order_by(RefundRequest.created_at.desc())
        )
        all_requests = list(request_rows.scalars().all())
        for refund_request in all_requests:
            requests_by_order.setdefault(refund_request.order_id, refund_request)

    # Refunded totals for the page, so each row can show what came back and
    # what is still refundable rather than inferring it from the status.
    refunded_totals = await RefundService(db).get_refunded_totals(
        [o.lemonsqueezy_order_id for o in orders]
    )

    refund_cutoff = datetime.now(timezone.utc) - timedelta(
        days=REFUND_REQUEST_WINDOW_DAYS
    )

    # Orders with a request still in flight. "In flight" is the same test
    # RefundRequestService.create_request applies — waiting to be reviewed, or
    # approved and waiting to be paid out — so the button this drives is
    # offered exactly when the request endpoint would accept it.
    #
    # Deliberately not keyed on the latest request alone: a finished request
    # (approved, refund_id set) must not block, or a customer refunded $25 of
    # $100 could never ask for the remaining $75.
    orders_with_open_request = {
        req.order_id
        for req in all_requests
        if req.status == RefundRequestStatus.PENDING
        or (
            req.status == RefundRequestStatus.APPROVED and req.refund_id is None
        )
    }

    def _ineligible_reason(order) -> Optional[str]:
        """Why this order cannot be refund-requested, or None if it can.

        Returned to the client so a missing button can explain itself. Without
        it the refund window in particular is invisible: the control simply
        disappears once a purchase ages past it, which reads as a bug to the
        customer and as a mystery to whoever answers their email.

        The wording matches what the request endpoint would reply, so the page
        and the API never tell the customer different things.
        """
        status_val = order.status.value if hasattr(order.status, "value") else str(order.status or "")
        if status_val.lower() not in ("paid", "partial_refund"):
            return f"Only paid orders can be refunded. This order is {status_val or 'unknown'}."
        if refundable_amount(
            order, refunded_totals.get(order.lemonsqueezy_order_id, 0)
        ) <= 0:
            return "This order has already been fully refunded."
        if order.id in orders_with_open_request:
            return "You already have a refund request open for this order."
        placed_at = order.ordered_at or order.created_at
        if placed_at is None:
            return "We can't tell when this order was placed."
        if placed_at.tzinfo is None:
            placed_at = placed_at.replace(tzinfo=timezone.utc)
        if placed_at < refund_cutoff:
            return (
                f"Refunds can only be requested within "
                f"{REFUND_REQUEST_WINDOW_DAYS} days of purchase."
            )
        return None

    def _can_request(order) -> bool:
        """Mirror the server-side eligibility rules for this order."""
        return _ineligible_reason(order) is None

    rows = []
    for order in orders:
        req = requests_by_order.get(order.id)
        req_status_str = None
        if req and req.status is not None:
            req_status_str = (
                req.status.value
                if hasattr(req.status, "value")
                else str(req.status)
            )
        order_status_str = (
            order.status.value
            if hasattr(order.status, "value")
            else str(order.status or "pending")
        )
        refunded_amt = refunded_totals.get(order.lemonsqueezy_order_id, 0)
        refundable_amt = refundable_amount(order, refunded_amt)

        rows.append(
            {
                "id": str(order.id),
                "lemonsqueezy_order_id": order.lemonsqueezy_order_id,
                "product_name": order.product_name,
                "status": order_status_str,
                "total": order.total or 0,
                "subtotal": order.subtotal,
                "tax": order.tax,
                "currency": order.currency,
                "receipt_url": order.receipt_url,
                "customer_email": current_user.get("email"),
                "subscription_id": str(order.subscription_id) if order.subscription_id else None,
                "ordered_at": order.ordered_at,
                "refunded_at": order.refunded_at,
                "created_at": order.created_at,
                "refund_request_status": req_status_str,
                "refund_requested_at": req.created_at if req else None,
                "refund_admin_note": req.admin_note if req else None,
                "can_request_refund": _can_request(order),
            "refund_ineligible_reason": _ineligible_reason(order),
                "refunded_amount": refunded_amt,
                "refundable_amount": refundable_amt,
            }
        )

    return success(
        data={"orders": rows, "count": len(rows)},
        request=request,
        message="Orders retrieved successfully"
    )


@router.get("/invoices", response_model=SuccessResponse[InvoiceListResponse])
@db_transaction_handler("get invoices", "Invoices retrieved successfully", auto_commit=False)
async def get_invoices(
    request: Request,
    limit: int = Query(10, ge=1, description="Maximum number of invoices to return"),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get invoice history for current user.

    Returns list of invoices from LemonSqueezy for the current user's subscription.
    Invoices include payment receipts, billing details, and downloadable PDFs.

    Query Parameters:
    - limit: Maximum number of invoices to return (default: 10)

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

    if not user:
        return success(
            data={"invoices": [], "count": 0},
            request=request,
            message="No invoices found"
        )

    # Serve from our own orders table when we have it. LemonSqueezy raises an
    # order for every charge, so this covers first purchases and renewals alike
    # without a network call on the billing page's critical path.
    local_result = await db.execute(
        select(Order)
        .where(Order.user_id == user_id)
        .order_by(Order.ordered_at.desc().nullslast(), Order.created_at.desc())
        .limit(limit)
    )
    local_orders = local_result.scalars().all()

    if local_orders:
        invoices = [
            order_to_invoice_dict(order, customer_email=current_user.get("email"))
            for order in local_orders
        ]

        # Also fetch completed refund records to render separate refund credit invoices
        refund_result = await db.execute(
            select(Refund)
            .where(
                Refund.user_id == user_id,
                Refund.status == RefundStatus.COMPLETED,
            )
            .order_by(Refund.created_at.desc())
        )
        local_refunds = refund_result.scalars().all()

        for refund in local_refunds:
            status_str = "partial_refund" if refund.is_partial else "refunded"
            ref_id = refund.lemonsqueezy_refund_id or f"REF-{refund.lemonsqueezy_order_id}"
            created_date = refund.processed_at or refund.created_at
            refund_inv = {
                "invoice_id": f"{ref_id}-{str(refund.id)[:8]}",
                # Suffixed with the refund's own id: one order can have
                # several partial refunds, and each is its own credit line.
                "invoice_number": f"REF-{refund.lemonsqueezy_order_id}-{str(refund.id)[:8]}",
                "subscription_id": str(refund.subscription_id) if refund.subscription_id else None,
                "status": status_str,
                "amount": (refund.refund_amount or 0) / 100.0,
                "subtotal": (refund.refund_amount or 0) / 100.0,
                "tax": 0.0,
                "currency": refund.currency or "USD",
                "invoice_url": None,
                "invoice_date": created_date,
                "due_date": None,
                "paid_at": created_date,
                "customer_email": current_user.get("email"),
                "customer_name": None,
                "items": [
                    {
                        "description": f"Refund Credit for Order #{refund.lemonsqueezy_order_id}" + (f" ({refund.reason})" if refund.reason else ""),
                        "quantity": 1,
                        "unit_price": (refund.refund_amount or 0) / 100.0,
                        "total": (refund.refund_amount or 0) / 100.0,
                    }
                ],
            }
            invoices.append(refund_inv)

        # Sort purchases and refund credits together, newest first. Both sides
        # carry datetimes here, so this compares dates rather than the two
        # different string renderings of them.
        _epoch = datetime.min.replace(tzinfo=timezone.utc)

        def _sort_key(invoice):
            value = invoice.get("invoice_date")
            if not isinstance(value, datetime):
                return _epoch
            return value if value.tzinfo else value.replace(tzinfo=timezone.utc)

        invoices.sort(key=_sort_key, reverse=True)

        return success(
            data={"invoices": invoices, "count": len(invoices)},
            request=request,
            message="Invoices retrieved successfully"
        )

    # No local orders: fall back to LemonSqueezy. This covers customers whose
    # purchases predate local order recording, until they are backfilled.
    logger.info(
        f"No local orders for user {user_id}, falling back to LemonSqueezy API"
    )

    # Collect the user's LemonSqueezy subscription ids so recurring invoices
    # (renewals / plan changes / refunds) can be fetched. These live on
    # /subscription-invoices and are only filterable by subscription_id.
    sub_result = await db.execute(
        select(UserSubscription.lemonsqueezy_subscription_id).where(
            UserSubscription.user_id == user_id,
            UserSubscription.lemonsqueezy_subscription_id.is_not(None),
        )
    )
    subscription_ids = [row[0] for row in sub_result.all() if row[0]]

    # Get payment provider
    payment_provider = get_payment_provider_singleton()

    def _iso(value):
        return value.isoformat() if hasattr(value, "isoformat") else (value or None)

    try:
        # Get invoices from payment provider (orders + subscription invoices)
        invoices_data = await payment_provider.get_invoices(
            user_email=user.email,
            limit=limit,
            subscription_ids=subscription_ids,
        )

        # Format invoices
        invoices = []
        for inv_data in invoices_data:
            invoice = Invoice(
                invoice_id=str(inv_data.get("invoice_id") or ""),
                invoice_number=str(inv_data.get("invoice_number") or inv_data.get("invoice_id") or ""),
                status=inv_data.get("status", "unknown"),
                amount=inv_data.get("amount", 0.0),
                currency=inv_data.get("currency", "USD"),
                tax=inv_data.get("tax"),
                subtotal=inv_data.get("subtotal"),
                invoice_url=inv_data.get("invoice_url"),
                invoice_date=_iso(inv_data.get("invoice_date")),
                due_date=_iso(inv_data.get("due_date")),
                paid_at=_iso(inv_data.get("paid_at")),
                customer_email=inv_data.get("customer_email"),
                customer_name=inv_data.get("customer_name"),
                items=inv_data.get("items", [])
            )
            invoices.append(invoice.model_dump())

        return success(
            data={
                "invoices": invoices,
                "count": len(invoices)
            },
            request=request,
            message=f"Retrieved {len(invoices)} invoice(s)"
        )

    except Exception as e:
        logger.error(
            "Failed to retrieve invoices",
            exc_info=True,
            extra={"user_id": str(user_id)}
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

def _refund_request_row(request) -> dict:
    """Serialise a refund request for API responses."""
    return {
        "id": request.id,
        "user_id": request.user_id,
        "order_id": request.order_id,
        "lemonsqueezy_order_id": request.lemonsqueezy_order_id,
        "requested_amount": request.requested_amount,
        "currency": request.currency,
        "reason": request.reason,
        "status": request.status.value if hasattr(request.status, "value") else str(request.status or "pending"),
        "admin_note": request.admin_note,
        "reviewed_at": request.reviewed_at,
        "refund_id": request.refund_id,
        "created_at": request.created_at,
        "product_name": request.order.product_name if request.order else None,
        "order_total": request.order.total if request.order else None,
    }


@router.post(
    "/refund-requests",
    response_model=SuccessResponse[RefundRequestRow],
    status_code=status.HTTP_201_CREATED,
)
@db_transaction_handler("create refund request")
async def create_refund_request(
    request: Request,
    body: RefundRequestCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Ask a super admin to refund one of your orders.

    This does not move any money. It raises a request for review; an admin
    approving it is what triggers the refund with the payment provider.

    Eligibility is enforced server-side: the order must be yours, paid, not
    already refunded, within the refund window, and without an open request.
    """
    user_id = current_user.get("identity")
    service = RefundRequestService(db)

    try:
        refund_request = await service.create_request(
            user_id=user_id,
            lemonsqueezy_order_id=body.lemonsqueezy_order_id,
            reason=body.reason,
            # Validated against the order's remaining balance in the service,
            # so a customer cannot ask for more than is left.
            requested_amount=body.requested_amount,
        )
    except RefundRequestError as exc:
        # These messages are written for the customer.
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    await db.commit()
    stored = await service.get(refund_request.id)

    # Tell the people who can act on it, in-app and by email, and acknowledge
    # to the customer that we have it. Best-effort: a notification failure must
    # not lose a request the customer already submitted, and email goes out
    # because an admin who is not logged in would otherwise never learn a
    # request is waiting.
    try:
        amount = (stored.requested_amount or 0) / 100
        formatted_amount = f"{amount:.2f} {stored.currency}"
        customer_email = stored.user.email if stored.user else "A customer"
        product_name = stored.order.product_name if stored.order else "Purchase"
        requested_date = stored.created_at.strftime("%B %-d, %Y")

        for admin_id in await service.get_super_admin_ids():
            await schedule_if_allowed(
                db=db,
                user_id=str(admin_id),
                background_tasks=background_tasks,
                pref_flag="billing_refund_requested",
                message=f"{customer_email} requested a {formatted_amount} refund",
                payload={
                    "refund_request_id": str(stored.id),
                    "lemonsqueezy_order_id": stored.lemonsqueezy_order_id,
                },
            )

            # Queued in the background so a slow mail provider never delays the
            # customer's response, and on its own session because this request's
            # one is closed before background tasks run.
            background_tasks.add_task(
                send_billing_email_in_background,
                "send_refund_requested_admin_email",
                admin_user_id=admin_id,
                customer_email=customer_email,
                product_name=product_name,
                refund_amount=formatted_amount,
                order_id=stored.lemonsqueezy_order_id,
                reason=stored.reason,
                requested_date=requested_date,
            )

        # And a receipt for the customer, so the request does not vanish into
        # silence while it waits for review.
        background_tasks.add_task(
            send_billing_email_in_background,
            "send_refund_request_received_email",
            user_id=stored.user_id,
            product_name=product_name,
            refund_amount=formatted_amount,
            order_id=stored.lemonsqueezy_order_id,
            requested_date=requested_date,
        )
    except Exception:
        logger.warning("Failed to notify about refund request", exc_info=True)

    return success(
        data=_refund_request_row(stored),
        request=request,
        message="Refund request submitted",
    )


@router.get(
    "/refund-requests",
    response_model=SuccessResponse[RefundRequestListResponse],
)
@db_transaction_handler("list refund requests", auto_commit=False)
async def list_my_refund_requests(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
):
    """List your own refund requests and their review status."""
    user_id = current_user.get("identity")
    requests = await RefundRequestService(db).list_for_user(user_id)

    return success(
        data={"data": [_refund_request_row(r) for r in requests]},
        request=request,
        message="Refund requests retrieved successfully",
    )


async def _get_user_ls_subscription_id(db: AsyncSession, user_id) -> str:
    """Return the user's LemonSqueezy subscription id, or 400 if there is none.

    Trial and free users have no LemonSqueezy subscription, so none of the
    billing management actions below apply to them.
    """
    result = await db.execute(
        select(UserSubscription.lemonsqueezy_subscription_id)
        .where(
            UserSubscription.user_id == user_id,
            UserSubscription.lemonsqueezy_subscription_id.is_not(None),
        )
        .order_by(UserSubscription.created_at.desc())
    )
    ls_subscription_id = result.scalars().first()

    if not ls_subscription_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active paid subscription to manage."
        )

    return ls_subscription_id


@router.get("/billing-urls", response_model=SuccessResponse[BillingUrlsResponse])
@db_transaction_handler("get billing urls", auto_commit=False)
async def get_billing_urls(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
    _rate_limit: None = Depends(customer_portal_rate_limit())
):
    """
    Get LemonSqueezy's signed billing URLs for the current user.

    LemonSqueezy expires these after roughly 24 hours, so they are fetched on
    demand rather than stored.

    Returns:
    - update_payment_method: frameable, so it opens in the on-site overlay
    - customer_portal: a full portal page that refuses framing, so it can only
      open in a new tab. Needed only for tax IDs and billing addresses.
    """
    user_id = current_user.get("identity")
    ls_subscription_id = await _get_user_ls_subscription_id(db, user_id)

    try:
        urls = await get_payment_provider_singleton().get_subscription_urls(
            ls_subscription_id
        )
    except Exception:
        logger.error("Failed to fetch subscription URLs", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not reach the payment provider. Please try again."
        )

    return success(
        data={
            "update_payment_method": urls.get("update_payment_method"),
            "customer_portal": urls.get("customer_portal"),
        },
        request=request,
        message="Billing URLs retrieved successfully"
    )


@router.post("/pause", response_model=SuccessResponse[SubscriptionCancelResponse])
@db_transaction_handler("pause subscription")
async def pause_subscription(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Pause the current subscription.

    Uses LemonSqueezy's "void" mode, so billing and access both stop. The
    subscription_paused webhook updates our local record.
    """
    user_id = current_user.get("identity")
    ls_subscription_id = await _get_user_ls_subscription_id(db, user_id)

    try:
        await get_payment_provider_singleton().pause_subscription(ls_subscription_id)
    except Exception:
        logger.error("Failed to pause subscription", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not pause the subscription. Please try again."
        )

    subscription = await SubscriptionService(db).get_subscription_by_user(user_id)

    return success(
        data={"subscription": subscription.to_dict() if subscription else None},
        request=request,
        message="Subscription paused"
    )


@router.post("/resume", response_model=SuccessResponse[SubscriptionCancelResponse])
@db_transaction_handler("resume subscription")
async def resume_subscription(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Resume a paused subscription.

    The subscription_resumed webhook updates our local record.
    """
    user_id = current_user.get("identity")
    ls_subscription_id = await _get_user_ls_subscription_id(db, user_id)

    try:
        await get_payment_provider_singleton().resume_subscription(ls_subscription_id)
    except Exception:
        logger.error("Failed to resume subscription", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not resume the subscription. Please try again."
        )

    subscription = await SubscriptionService(db).get_subscription_by_user(user_id)

    return success(
        data={"subscription": subscription.to_dict() if subscription else None},
        request=request,
        message="Subscription resumed"
    )


@router.api_route("/portal", methods=["GET", "POST"], response_model=dict, status_code=status.HTTP_200_OK)
@db_transaction_handler("create portal session", auto_commit=False)
async def create_portal_session(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
    _rate_limit: None = Depends(customer_portal_rate_limit())
):
    """
    Create billing portal session.
    """
    user_id = current_user.get("identity")
    service = SubscriptionService(db)

    # Get portal URL
    portal_url = await service.get_customer_portal_url(
        user_id=user_id,
        return_url=str(request.url_for("get_my_subscription"))
    )

    if not portal_url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No billing account found. Please subscribe to a plan first."
        )

    return success(
        data={"portal_url": portal_url},
        request=request,
        message="Portal session created successfully"
    )

@router.get("/status", response_model=SuccessResponse[SubscriptionStatusResponse])
@db_transaction_handler("get subscription status", auto_commit=False)
async def get_subscription_status(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get current subscription status with usage metrics. (Legacy support)
    """
    user_id = current_user.get("identity")
    service = SubscriptionService(db)
    usage_service = UsageTrackingService(db)

    subscription = await service.get_subscription_by_user(user_id)
    usage = await usage_service.get_usage_metrics(user_id)

    portal_url = await service.get_customer_portal_url(
        user_id=user_id,
        return_url=str(request.url_for("get_my_subscription"))
    )

    return success(
        data={
            "subscription": subscription.to_dict() if subscription else None,
            "plan": subscription.plan.to_dict() if subscription and subscription.plan else None,
            "usage": usage,
            "portal_url": portal_url
        },
        request=request,
        message="Subscription status retrieved successfully"
    )
