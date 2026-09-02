"""
User Subscription API endpoints.

This module provides subscription management operations for end users.
Routes handle HTTP concerns and delegate business logic to SubscriptionService.
"""

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.config import get_settings
from src.api.database.async_database import get_async_db
from src.api.middleware.exceptions import ResourceNotFoundException
from src.api.middleware.rate_limiter import (
    checkout_rate_limit,
    customer_portal_rate_limit,
    subscription_cancel_rate_limit,
    subscription_update_rate_limit,
)
from src.api.models.subscription_models.licenses import License
from src.api.models.subscription_models.subscriptions import UserSubscription
from src.api.models.user_models.users import Users
from src.api.schema.response.checkout_responses import (
    CheckoutSessionResponse,
    SubscriptionStatusResponse,
    UsageMetricsResponse,
)
from src.api.schema.response.subscription_responses import (
    InvoiceListResponse,
    SubscriptionCancelResponse,
    SubscriptionDetails,
    SubscriptionHistoryResponse,
    SubscriptionUpgradeResponse,
)
from src.api.schema.response.trial_responses import TrialStatusResponse
from src.api.schema.response_schemas import SuccessResponse
from src.api.schema.subscription import (
    CheckoutSessionRequest,
    Invoice,
    SubscriptionCancelRequest,
    SubscriptionCreateRequest,
    SubscriptionUpgradeRequest,
)
from src.api.schema.subscription.enums import BillingPeriod
from src.api.security.dependencies import get_current_user
from src.config.payment_config import payment_settings
from src.providers.payment.provider_factory import get_payment_provider_singleton
from src.services.notification_helper import schedule_if_allowed
from src.services.subscription_plan_service import SubscriptionPlanService
from src.services.subscription_service import SubscriptionService
from src.services.usage_tracking_service import UsageTrackingService
from src.utils.logger import logger
from src.utils.response_utils import success
from src.utils.route_decorators import db_transaction_handler

settings = get_settings()

router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])


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
            logger.error(
                f"Failed to send subscription cancellation email for user {user_id}: {exc}"
            )


@router.post(
    "/subscribe",
    response_model=SuccessResponse[SubscriptionDetails],
    status_code=status.HTTP_201_CREATED,
)
@db_transaction_handler("subscribe to plan")
async def subscribe_to_plan(
    request: Request,
    subscription_data: SubscriptionCreateRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
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
        billing_period=subscription_data.billing_period,
    )

    # Get plan name for response
    plan = await service.get_plan_by_id(subscription_data.plan_id)

    # Build response
    response_data = new_subscription.to_dict()
    response_data["plan_name"] = plan.name
    response_data["plan_display_name"] = plan.display_name

    return success(data=response_data, request=request, message="Subscribed to plan successfully")


@router.post(
    "/checkout",
    response_model=SuccessResponse[CheckoutSessionResponse],
    status_code=status.HTTP_200_OK,
)
@db_transaction_handler("create checkout session")
async def create_checkout_session(
    request: Request,
    checkout_data: CheckoutSessionRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
    _rate_limit: None = Depends(checkout_rate_limit()),
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
        affiliate_code=checkout_data.affiliate_code,
    )

    logger.info(f"Checkout session created for user {user_id}")
    return success(
        data=checkout_session, request=request, message="Checkout session created successfully"
    )


@router.get("/credits", status_code=status.HTTP_200_OK)
@db_transaction_handler("get credit balance", auto_commit=False)
async def get_credit_balance(
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Return current credit balance for the authenticated user."""
    from sqlalchemy import and_
    from sqlalchemy import select as sa_select
    from sqlalchemy.orm import selectinload

    from src.api.models.subscription_models.subscriptions import (
        UserSubscription,
        subscription_grants_access,
    )

    user_id = current_user.get("identity")
    result = await db.execute(
        sa_select(UserSubscription)
        .options(selectinload(UserSubscription.plan))
        .where(
            and_(
                UserSubscription.user_id == user_id,
                subscription_grants_access(),
            )
        )
        .order_by(UserSubscription.start_date.desc())
        .limit(1)
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
            "credits_reset_date": subscription.credits_reset_date.isoformat()
            if subscription.credits_reset_date is not None
            else None,
            "articles_remaining": None if unlimited else max(0, credits // 15),
            "plan_name": plan.display_name if plan else None,
        },
        message="Credit balance retrieved.",
    )


@router.get("/my-subscription", response_model=SuccessResponse[SubscriptionDetails])
@router.get(
    "/current", response_model=SuccessResponse[SubscriptionDetails]
)  # Alias for compatibility
@db_transaction_handler(
    "get my subscription", "Subscription retrieved successfully", auto_commit=False
)
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

    if not subscription:
        return success(
            data={"subscription": None}, request=request, message="No active subscription found"
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
        "max_api_calls_per_month": plan.max_api_calls_per_month,
    }

    # Add current_period_end as alias for renews_at (frontend compatibility)
    if subscription.renews_at:
        response_data["current_period_end"] = (
            subscription.renews_at.isoformat()
            if hasattr(subscription.renews_at, "isoformat")
            else subscription.renews_at
        )

    # Add customer portal URL if subscription exists with payment provider
    portal_url = await service.get_customer_portal_url(
        user_id=user_id, return_url=str(request.url_for("get_my_subscription"))
    )
    response_data["customer_portal_url"] = portal_url

    # Add usage metrics if requested
    if include_usage:
        current_usage = await service.calculate_usage(user_id)
        response_data["current_usage"] = {
            "workspaces": current_usage["workspaces"],
            "topics": current_usage["topics"],
            "knowledge_items": current_usage["knowledge_items"],
            "api_calls": subscription.current_api_calls,
        }

    # Add available plans for discovery
    plan_service = SubscriptionPlanService(db)
    available_plans = await plan_service.list_plans(
        include_inactive=False, include_private=False, is_admin=False
    )
    response_data["plans"] = available_plans.get("plans", [])

    # Add user licenses
    license_result = await db.execute(select(License).where(License.user_id == user_id))
    licenses = license_result.scalars().all()
    response_data["licenses"] = [lic.to_dict() for lic in licenses]
    response_data["activations_count"] = sum(lic.activation_count for lic in licenses)

    # Schedule expiring notification if renewal is near (within 3 days)
    if subscription.renews_at:
        from datetime import datetime, timezone

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
                payload={
                    "subscription_id": str(subscription.id),
                    "renewal_date": subscription.renews_at.isoformat(),
                },
            )
    return success(
        data={"subscription": response_data},
        request=request,
        message="Subscription retrieved successfully",
    )


# NOTE: /status endpoint is in checkout_routes.py (includes portal URL and free tier usage)


@router.get("/history", response_model=SuccessResponse[SubscriptionHistoryResponse])
@db_transaction_handler("get subscription history", auto_commit=False)
async def get_subscription_history(
    request: Request,
    limit: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
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
        data={"subscriptions": subscriptions_data, "count": len(subscriptions_data)},
        request=request,
        message=f"Retrieved {len(subscriptions_data)} subscription(s)",
    )


@router.post("/upgrade", response_model=SuccessResponse[SubscriptionUpgradeResponse])
@db_transaction_handler("upgrade subscription")
async def upgrade_subscription(
    request: Request,
    upgrade_data: SubscriptionUpgradeRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
    _rate_limit: None = Depends(subscription_update_rate_limit()),
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
            status_code=400, detail="new_plan_id is required and must be a valid UUID"
        )

    # Fetch the new plan
    new_plan = await service.get_plan_by_id(upgrade_data.new_plan_id)
    if not new_plan:
        raise HTTPException(status_code=404, detail="The specified plan does not exist")

    # Fetch current subscription
    current_subscription = await service.get_subscription_by_user(user_id)
    if not current_subscription:
        raise HTTPException(status_code=404, detail="Current subscription not found")

    # Prevent upgrade to lower plan accidentally
    current_plan_price = (
        float(current_subscription.plan.price_monthly or 0) if current_subscription.plan else 0
    )
    new_plan_price = float(new_plan.price_monthly or 0)
    if new_plan_price < current_plan_price:
        raise HTTPException(
            status_code=400,
            detail="Cannot upgrade to a lower-priced plan. Use downgrade endpoint instead.",
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
            message="Payment required to upgrade. Redirect user to checkout_url.",
        )

    # Paid → paid: provider handles proration billing automatically
    updated_subscription = await service.upgrade(
        user_id=user_id,
        new_plan_id=upgrade_data.new_plan_id,
        billing_period=upgrade_data.billing_period,
    )

    response_data = updated_subscription.to_dict()
    response_data["plan_name"] = new_plan.name
    response_data["plan_display_name"] = new_plan.display_name

    return success(
        data=response_data,
        request=request,
        message=f"Successfully upgraded to {new_plan.display_name}",
    )


# downgrade route
@router.post("/downgrade", response_model=SuccessResponse[SubscriptionUpgradeResponse])
@db_transaction_handler("downgrade subscription")
async def downgrade_subscription(
    request: Request,
    downgrade_data: SubscriptionUpgradeRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
    _rate_limit: None = Depends(subscription_update_rate_limit()),
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
        raise HTTPException(status_code=400, detail="plan id is required")
    # Fetch current subscription and plan
    subscription = await service.get_subscription_by_user(user_id)
    if not subscription:
        raise HTTPException(status_code=404, detail="No active subscription found")
    current_plan = await service._get_plan_or_404(subscription.plan_id)

    # Fetch new plan
    new_plan = await service.get_plan_by_id(downgrade_data.new_plan_id)

    # Prevent downgrade to higher plan
    current_plan_price = float(current_plan.price_monthly or 0)
    new_plan_price = float(new_plan.price_monthly or 0)
    if new_plan_price > current_plan_price:
        raise HTTPException(
            status_code=400, detail="Use upgrade subscription to move to the higher plan"
        )

    # Downgrade subscription (same logic as upgrade)
    updated_subscription = await service.upgrade(
        user_id=user_id,
        new_plan_id=downgrade_data.new_plan_id,
        billing_period=downgrade_data.billing_period,
    )

    # Build response
    response_data = updated_subscription.to_dict()
    response_data["plan_name"] = new_plan.name
    response_data["plan_display_name"] = new_plan.display_name

    return success(
        data=response_data,
        request=request,
        message=f"Successfully downgraded to {new_plan.display_name}",
    )


@router.post("/cancel", response_model=SuccessResponse[SubscriptionCancelResponse])
@db_transaction_handler("cancel subscription")
async def cancel_subscription(
    request: Request,
    cancel_data: SubscriptionCancelRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
    _rate_limit: None = Depends(subscription_cancel_rate_limit()),
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
        background_tasks=background_tasks,
    )

    if not subscription:
        raise ResourceNotFoundException(
            resource_type="subscription", message="No active subscription found to cancel"
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
            end_date=subscription.end_date.strftime("%B %d, %Y")
            if subscription.end_date
            else "the end of your billing period",
        )

    # Return raw data - decorator handles success response formatting
    return success(data=subscription.to_dict(), request=request, message=message)


@router.get("/usage", response_model=SuccessResponse[UsageMetricsResponse])
@db_transaction_handler(
    "get usage stats", "Usage statistics retrieved successfully", auto_commit=False
)
async def get_usage_stats(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
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
        data=usage_data, request=request, message="Usage statistics retrieved successfully"
    )


@router.get("/trial-status", response_model=SuccessResponse[TrialStatusResponse])
@db_transaction_handler(
    "get trial status", "Trial status retrieved successfully", auto_commit=False
)
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
        from datetime import datetime, timezone

        trial_end = datetime.fromisoformat(trial_data["trial_end_date"]).replace(
            tzinfo=timezone.utc
        )
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
    return success(data=trial_data, request=request, message="Trial status retrieved successfully")


@router.get("/invoices", response_model=SuccessResponse[InvoiceListResponse])
@db_transaction_handler("get invoices", "Invoices retrieved successfully", auto_commit=False)
async def get_invoices(
    request: Request,
    limit: int = Query(10, ge=1, le=100, description="Maximum number of invoices to return"),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
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
    result = await db.execute(select(Users).where(Users.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        return success(
            data={"invoices": [], "count": 0}, request=request, message="No invoices found"
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
                invoice_number=str(
                    inv_data.get("invoice_number") or inv_data.get("invoice_id") or ""
                ),
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
                items=inv_data.get("items", []),
            )
            invoices.append(invoice.model_dump())

        return success(
            data={"invoices": invoices, "count": len(invoices)},
            request=request,
            message=f"Retrieved {len(invoices)} invoice(s)",
        )

    except Exception:
        logger.error("Failed to retrieve invoices", exc_info=True, extra={"user_id": str(user_id)})
        # Return empty list on error rather than failing
        return success(
            data={"invoices": [], "count": 0},
            request=request,
            message="Unable to retrieve invoices at this time",
        )


@router.api_route(
    "/portal", methods=["GET", "POST"], response_model=dict, status_code=status.HTTP_200_OK
)
@db_transaction_handler("create portal session", auto_commit=False)
async def create_portal_session(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
    _rate_limit: None = Depends(customer_portal_rate_limit()),
):
    """
    Create billing portal session.
    """
    user_id = current_user.get("identity")
    service = SubscriptionService(db)

    # Get portal URL
    portal_url = await service.get_customer_portal_url(
        user_id=user_id, return_url=str(request.url_for("get_my_subscription"))
    )

    if not portal_url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No billing account found. Please subscribe to a plan first.",
        )

    return success(
        data={"portal_url": portal_url},
        request=request,
        message="Portal session created successfully",
    )


@router.get("/status", response_model=SuccessResponse[SubscriptionStatusResponse])
@db_transaction_handler("get subscription status", auto_commit=False)
async def get_subscription_status(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
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
        user_id=user_id, return_url=str(request.url_for("get_my_subscription"))
    )

    return success(
        data={
            "subscription": subscription.to_dict() if subscription else None,
            "plan": subscription.plan.to_dict() if subscription and subscription.plan else None,
            "usage": usage,
            "portal_url": portal_url,
        },
        request=request,
        message="Subscription status retrieved successfully",
    )
