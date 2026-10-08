"""
Admin Refund Management API endpoints.

This module provides administrative operations for managing refunds including:
- Creating refunds via LemonSqueezy API
- Viewing refund history
- Tracking refund status

All endpoints require super admin permissions.
"""

from datetime import datetime, timezone
from typing import Dict, Optional, Sequence, Tuple
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from src.api.database.async_database import get_async_db
from src.api.models.subscription_models.licenses import License
from src.api.models.subscription_models.orders import Order, OrderStatus
from src.api.models.subscription_models.refund_requests import (
    RefundRequest,
    RefundRequestStatus,
)
from src.api.models.subscription_models.refunds import Refund, RefundStatus
from src.api.models.subscription_models.subscriptions import UserSubscription
from src.api.models.user_models.users import Users
from src.api.schema.response.refund_responses import (
    RefundableOrderListResponse,
    RefundAdminListResponse,
    RefundAdminRow,
    RefundCreateData,
    RefundRequestListResponse,
    RefundRequestRow,
)
from src.api.schema.response_schemas import SuccessResponse
from src.api.schema.subscription.refund_schemas import (
    AdminRefundRequestCreate,
    RefundCreateRequest,
    RefundRequestReview,
)
from src.api.security.dependencies import get_current_user
from src.config.payment_config import payment_settings
from src.providers.payment.provider_factory import get_payment_provider_singleton
from src.providers.payment.providers.lemonsqueezy import (
    LemonSqueezyAPIError,
    LemonSqueezyError,
    LemonSqueezyProvider,
    LemonSqueezyTransientError,
)
from src.services.audit_logger import audit_logger
from src.services.billing_email_service import send_billing_email_in_background
from src.services.notification_helper import schedule_if_allowed
from src.services.order_service import (
    OrderService,
    apply_refund_state,
    refundable_amount,
)
from src.services.plan_change_charges import PlanChangeCharge, plan_change_charges_for_orders
from src.services.refund_cancellation import (
    cancel_at_provider_for_refund,
    end_for_refund,
    no_subscription_to_end,
    refunded_subscription,
)
from src.services.refund_request_service import (
    RefundRequestError,
    RefundRequestService,
)
from src.services.refund_service import RefundService
from src.services.usage_tracking_service import UsageTrackingService
from src.utils.logger import logger
from src.utils.response_utils import success
from src.utils.route_decorators import db_transaction_handler, require_permissions

from .shared.auth import require_super_admin

router = APIRouter()


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


async def get_lemonsqueezy_provider() -> LemonSqueezyProvider:
    """The shared Lemon Squeezy provider (G80a): one built per refund opened an HTTP client that
    nothing closed."""
    if not payment_settings.lemonsqueezy_api_key or not payment_settings.lemonsqueezy_store_id:
        raise HTTPException(status_code=503, detail="Payment provider is not configured")

    return get_payment_provider_singleton()


async def _issue_refund(
    db: AsyncSession,
    *,
    lemonsqueezy_order_id: str,
    user_id: UUID,
    subscription_id: Optional[UUID],
    amount: Optional[int],
    reason: Optional[str],
) -> Tuple[Optional[Refund], Dict[str, int]]:
    """Refund money against an order and record what LemonSqueezy actually did.

    The one place any refund is executed, so the admin's "Create refund" button
    and processing an approved customer request cannot drift apart on what is
    allowed or on how the result is recorded.

    Every amount here comes from LemonSqueezy's own copy of the order rather
    than from the caller: the order is read back first, so the paid amount and
    the amount already refunded are authoritative even if a refund was issued
    from the LemonSqueezy dashboard and we never saw the webhook.

    Args:
        lemonsqueezy_order_id: The order to refund against.
        user_id: The user being refunded.
        subscription_id: Local subscription, when the order came from one.
        amount: Cents to refund, or None for the whole remaining balance.
        reason: Stored on the refund record.

    Returns:
        The refund record written for this payout — None if LemonSqueezy
        reported nothing we had not already recorded — and the order's amounts
        afterwards: ``total``, ``refunded_amount`` and ``refundable_amount``,
        all in cents.

    Raises:
        HTTPException: If the order has no refundable balance left, or the
            requested amount exceeds it.
    """
    provider = await get_lemonsqueezy_provider()

    # Despite the name, this is GET /orders/{id} — the order carries both the
    # amount paid and the cumulative amount refunded.
    ls_order = await provider.get_refund(str(lemonsqueezy_order_id))
    attributes = ls_order.get("attributes", {}) or {}

    order_total = int(attributes.get("total") or 0)
    already_refunded = int(attributes.get("refunded_amount") or 0)
    currency = attributes.get("currency") or "USD"
    remaining = max(0, order_total - already_refunded)

    if order_total <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Order {lemonsqueezy_order_id} has no amount to refund.",
        )

    if remaining <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Order {lemonsqueezy_order_id} has already been fully "
                f"refunded ({already_refunded / 100:.2f} {currency})."
            ),
        )

    # A full refund is the remaining balance, not the original total: on an
    # order that was already partially refunded those differ.
    refund_amount = int(amount) if amount else remaining

    if refund_amount > remaining:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Refund of {refund_amount / 100:.2f} {currency} exceeds the "
                f"{remaining / 100:.2f} {currency} still refundable on this order."
            ),
        )

    ls_result = await provider.create_refund(
        order_id=str(lemonsqueezy_order_id),
        amount=refund_amount,
        reason=reason,
    )
    result_attributes = ls_result.get("attributes", {}) or {}

    # LemonSqueezy returns the order, whose refunded_amount is cumulative.
    # Falling back to the sum we know we asked for keeps the record correct if
    # a response ever omits it.
    provider_refunded_total = int(
        result_attributes.get("refunded_amount") or (already_refunded + refund_amount)
    )

    order_service = OrderService(db)
    order = await order_service.get_by_lemonsqueezy_id(str(lemonsqueezy_order_id))
    original_amount = (order.total if order else 0) or order_total

    refund_service = RefundService(db)
    refund = await refund_service.record_provider_refund(
        lemonsqueezy_order_id=str(lemonsqueezy_order_id),
        user_id=user_id,
        provider_refunded_total=provider_refunded_total,
        original_amount=original_amount,
        subscription_id=subscription_id,
        reason=reason,
        lemonsqueezy_refund_id=str(ls_result.get("id") or lemonsqueezy_order_id),
        currency=result_attributes.get("currency") or currency,
    )

    refunded_total = await refund_service.get_refunded_total(str(lemonsqueezy_order_id))

    if order:
        apply_refund_state(order, refunded_total)
        await db.flush()
        remaining_after = refundable_amount(order, refunded_total)
    else:
        remaining_after = max(0, original_amount - refunded_total)

    # A partial refund keeps the subscription, the license and all access, and
    # gives back only the unused share of the entitlement. Done here as well as
    # in the `order_refunded` webhook so the admin sees the balance move now
    # rather than whenever the webhook lands; it recomputes from the order's
    # cumulative totals rather than decrementing, so running twice is a no-op.
    if remaining_after > 0:
        adjustment = await UsageTrackingService(db).reconcile_partial_refund_credits(
            user_id=user_id,
            lemonsqueezy_order_id=str(lemonsqueezy_order_id),
            refunded_total=refunded_total,
            original_amount=original_amount,
        )
        if adjustment:
            logger.info(
                f"Reduced unused credits after partial refund on order "
                f"{lemonsqueezy_order_id}: "
                f"{adjustment['credits_before']} -> {adjustment['credits_after']}",
                extra={"order_id": str(lemonsqueezy_order_id), **adjustment},
            )

    else:
        # A full refund ends the subscription at Lemon Squeezy as well as here: left
        # active there, it renews and charges the refunded customer again, and its next
        # "active" update would give the plan back (F8c, revnix/rext-control#538). The
        # cancel is made once and recorded; a failed one alerts a person, and the
        # refund stands either way.
        subscription = await refunded_subscription(
            db,
            order_id=str(lemonsqueezy_order_id),
            user_id=user_id,
            order=order,
            subscription_id=subscription_id,
        )
        if subscription is not None:
            await cancel_at_provider_for_refund(
                subscription, order_id=str(lemonsqueezy_order_id), provider=provider
            )
            end_for_refund(subscription, order_id=str(lemonsqueezy_order_id))
            await db.flush()
        else:
            no_subscription_to_end(order_id=str(lemonsqueezy_order_id), user_id=user_id)

    return refund, {
        "total": original_amount,
        "refunded_amount": refunded_total,
        "refundable_amount": remaining_after,
    }


# ============================================================================
# REFUND ENDPOINTS
# ============================================================================


@router.get("/refunds", response_model=SuccessResponse[RefundAdminListResponse])
@require_permissions("billing.read")
@db_transaction_handler("list refunds", auto_commit=False)
async def list_refunds(
    request: Request,
    user_id: Optional[UUID] = Query(None, description="Filter by user ID"),
    subscription_id: Optional[UUID] = Query(None, description="Filter by subscription ID"),
    status: Optional[RefundStatus] = Query(
        None, description="Filter by status (pending/completed/failed)"
    ),
    is_partial: Optional[bool] = Query(None, description="Filter by partial refund status"),
    start_date: Optional[datetime] = Query(None, description="Start date filter (ISO format)"),
    end_date: Optional[datetime] = Query(None, description="End date filter (ISO format)"),
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(50, ge=1, le=200, description="Items per page"),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
):
    """
    List refunds with filtering and pagination (super admin only).

    Query Parameters:
    - user_id: Filter by user ID
    - subscription_id: Filter by subscription ID
    - status: Filter by status (pending/completed/failed)
    - is_partial: Filter by partial refund status
    - start_date: Start date filter (ISO format)
    - end_date: End date filter (ISO format)
    - page: Page number (default 1)
    - per_page: Items per page (default 50, max 200)

    Returns:
    - List of refunds with pagination and summary statistics
    """
    admin_user_id = current_user.get("identity")
    await require_super_admin(db, admin_user_id)

    service = RefundService(db)
    result = await service.list_refunds(
        user_id=user_id,
        subscription_id=subscription_id,
        status=status,
        is_partial=is_partial,
        start_date=start_date,
        end_date=end_date,
        page=page,
        per_page=per_page,
    )

    return success(data=result, request=request, message="Refunds retrieved successfully")


@router.get(
    "/refunds/orders",
    response_model=SuccessResponse[RefundableOrderListResponse],
)
@require_permissions("billing.read")
@db_transaction_handler("search refundable orders", auto_commit=False)
async def search_refundable_orders(
    request: Request,
    search: Optional[str] = Query(
        None,
        description="Match on customer email, name, product name or LemonSqueezy order id",
    ),
    status_filter: Optional[str] = Query(
        None, alias="status", description="Filter by order status, e.g. paid"
    ),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Search orders an admin can refund against (super admin only).

    Exists because admins previously had no way to discover the LemonSqueezy
    order id that creating a refund requires — they had to know it by heart.
    Every row returned here comes from our local `orders` table, so its order
    id is guaranteed to resolve when the refund is submitted.

    Query Parameters:
    - search: customer email, name, product name, or LemonSqueezy order id
    - status: order status filter (defaults to paid orders only)
    - page / per_page: pagination

    Returns:
    - Matching orders, newest first, each flagged with whether it has already
      been refunded
    """
    admin_user_id = current_user.get("identity")
    await require_super_admin(db, admin_user_id)

    filters = []

    if search:
        term = f"%{search.strip()}%"
        from sqlalchemy import String, cast

        filters.append(
            or_(
                Order.lemonsqueezy_order_id.ilike(term),
                cast(Order.subscription_id, String).ilike(term),
                cast(Order.id, String).ilike(term),
                Order.product_name.ilike(term),
                Users.email.ilike(term),
                Users.full_name.ilike(term),
            )
        )

    if status_filter:
        filters.append(Order.status == status_filter.lower())
    else:
        # Paid or partially refunded orders can be refunded.
        filters.append(Order.status.in_([OrderStatus.PAID, OrderStatus.PARTIAL_REFUND]))

    base = select(Order).join(Users, Users.id == Order.user_id)
    if filters:
        base = base.where(and_(*filters))

    count_result = await db.execute(select(func.count()).select_from(base.subquery()))
    total_items = count_result.scalar() or 0

    result = await db.execute(
        base.options(joinedload(Order.user))
        .order_by(Order.ordered_at.desc().nullslast(), Order.created_at.desc())
        .limit(per_page)
        .offset((page - 1) * per_page)
    )
    orders = result.unique().scalars().all()

    # One query for refunds across the page, rather than per row.
    refunded = await RefundService(db).get_refunded_totals(
        [o.lemonsqueezy_order_id for o in orders]
    )
    # What each customer paid for a plan change since: a refund of the order
    # doesn't give that back.
    plan_change = await plan_change_charges_for_orders(db, orders)

    rows = []
    for order in orders:
        refunded_so_far = refunded.get(order.lemonsqueezy_order_id, 0)
        remaining = refundable_amount(order, refunded_so_far)
        rows.append(
            {
                "id": order.id,
                "lemonsqueezy_order_id": order.lemonsqueezy_order_id,
                "user_id": order.user_id,
                "user_email": order.user.email if order.user else None,
                "user_name": order.user.full_name if order.user else None,
                "subscription_id": order.subscription_id,
                "product_name": order.product_name,
                "status": order.status.value if order.status else "pending",
                "total": order.total or 0,
                "currency": order.currency or "USD",
                "receipt_url": order.receipt_url,
                "ordered_at": order.ordered_at,
                "created_at": order.created_at,
                # An order is done only when nothing is left to refund. A
                # partial refund must not take it out of the picker: the rest
                # of the balance is still refundable.
                "already_refunded": remaining <= 0,
                "refunded_amount": refunded_so_far,
                "refundable_amount": remaining,
                "plan_change_charges": [
                    charge.as_row() for charge in plan_change.get(order.lemonsqueezy_order_id, ())
                ],
            }
        )

    total_pages = (total_items + per_page - 1) // per_page

    return success(
        data={
            "data": rows,
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total_items": total_items,
                "total_pages": total_pages,
            },
        },
        message="Refundable orders retrieved successfully",
    )


async def _notify_requester(
    *,
    db,
    background_tasks,
    refund_request,
    pref_flag: str,
    message: str,
    email_method: Optional[str] = None,
    email_kwargs: Optional[Dict[str, object]] = None,
) -> None:
    """Tell the customer the outcome, in the app and by email. Best-effort.

    The decision is already committed, so a notification failure must not
    surface as an error on an action that actually succeeded.

    Both channels are driven from here so no decision path can update one and
    forget the other. Each respects its own preference: `pref_flag` gates the
    in-app notice, and the email service checks the matching email preference.

    Args:
        email_method: BillingEmailService coroutine to queue, if any.
        email_kwargs: Its arguments.
    """
    try:
        await schedule_if_allowed(
            db=db,
            user_id=str(refund_request.user_id),
            background_tasks=background_tasks,
            pref_flag=pref_flag,
            message=message,
            payload={
                "refund_request_id": str(refund_request.id),
                "lemonsqueezy_order_id": refund_request.lemonsqueezy_order_id,
                "admin_note": refund_request.admin_note,
            },
        )
    except Exception:
        logger.warning("Failed to notify customer of refund decision", exc_info=True)

    if email_method:
        # Queued rather than awaited so a slow mail provider never delays the
        # admin's response, on its own session so it survives this request.
        background_tasks.add_task(
            send_billing_email_in_background, email_method, **(email_kwargs or {})
        )


def _admin_request_row(
    req, refunded_so_far: int = 0, plan_change: Sequence[PlanChangeCharge] = ()
) -> dict:
    """Serialise a refund request with the context an admin needs to judge it.

    Carries the order's money state as well as the request's own, because
    approving and processing are separate steps: the queue has to show whether
    an approved request still has a balance left to pay out. And what the
    customer paid for a plan change since, which this refund doesn't give back.
    """
    order_total = req.order.total if req.order else None
    remaining = refundable_amount(req.order, refunded_so_far) if req.order else 0
    return {
        "id": req.id,
        "user_id": req.user_id,
        "order_id": req.order_id,
        "lemonsqueezy_order_id": req.lemonsqueezy_order_id,
        "requested_amount": req.requested_amount,
        "currency": req.currency,
        "reason": req.reason,
        "status": req.status.value if req.status else "pending",
        "admin_note": req.admin_note,
        "reviewed_at": req.reviewed_at,
        "refund_id": req.refund_id,
        "created_at": req.created_at,
        "user_email": req.user.email if req.user else None,
        "user_name": req.user.full_name if req.user else None,
        "product_name": req.order.product_name if req.order else None,
        "order_total": order_total,
        "refunded_amount": refunded_so_far,
        "refundable_amount": remaining,
        # Approved but not yet paid out. This is what the "Process refund"
        # action keys off, and it is why approval alone moves no money.
        "awaiting_processing": (
            req.status == RefundRequestStatus.APPROVED and req.refund_id is None and remaining > 0
        ),
        "plan_change_charges": [charge.as_row() for charge in plan_change],
    }


async def _request_row_with_totals(db: AsyncSession, req) -> dict:
    """`_admin_request_row` for one request, with its order's refund total."""
    refunded = await RefundService(db).get_refunded_total(req.lemonsqueezy_order_id)
    plan_change = await plan_change_charges_for_orders(db, [req.order])
    return _admin_request_row(req, refunded, plan_change.get(req.lemonsqueezy_order_id, ()))


@router.get(
    "/refunds/requests",
    response_model=SuccessResponse[RefundRequestListResponse],
)
@require_permissions("billing.read")
@db_transaction_handler("list refund requests", auto_commit=False)
async def list_refund_requests(
    request: Request,
    status_filter: Optional[str] = Query(
        None, alias="status", description="pending, approved or rejected"
    ),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
):
    """
    List customer refund requests for review (super admin only).

    Pending requests sort first so the queue stays actionable.
    """
    await require_super_admin(db, current_user.get("identity"))

    result = await RefundRequestService(db).list_for_admin(
        status=status_filter, page=page, per_page=per_page
    )

    # One query for the page's refund totals rather than one per row.
    refunded = await RefundService(db).get_refunded_totals(
        [r.lemonsqueezy_order_id for r in result["requests"]]
    )
    plan_change = await plan_change_charges_for_orders(db, [r.order for r in result["requests"]])

    return success(
        data={
            "data": [
                _admin_request_row(
                    r,
                    refunded.get(r.lemonsqueezy_order_id, 0),
                    plan_change.get(r.lemonsqueezy_order_id, ()),
                )
                for r in result["requests"]
            ],
            "pagination": result["pagination"],
        },
        message="Refund requests retrieved successfully",
    )


@router.post(
    "/refunds/requests",
    response_model=SuccessResponse[RefundRequestRow],
    status_code=status.HTTP_201_CREATED,
)
@require_permissions("billing.manage")
@db_transaction_handler("log refund request")
async def create_refund_request_for_customer(
    request: Request,
    body: AdminRefundRequestCreate,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Log a refund a customer asked for by email (super admin only).

    Customers ask for refunds through support rather than in the app, so this
    is how their request enters the queue. It creates the request only — the
    admin still has to approve it and then process it, which keeps every
    refund on the same reviewed path and leaves an auditable trail of who
    decided what.

    The customer is taken from the order itself, so a request can never be
    filed against someone who did not place it. The refund window is not
    enforced here: a customer may have written in well within it even if the
    admin is only logging the email now, and the admin reviews it regardless.

    Request Body:
    - lemonsqueezy_order_id: The order the customer wants refunded
    - reason: Why they want it, in their words
    - requested_amount: Cents, for a partial request. Omit for the whole
      remaining refundable balance.
    """
    admin_user_id = current_user.get("identity")
    await require_super_admin(db, admin_user_id)

    order = await OrderService(db).get_by_lemonsqueezy_id(body.lemonsqueezy_order_id)
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No order found for {body.lemonsqueezy_order_id}",
        )

    service = RefundRequestService(db)

    try:
        refund_request = await service.create_request(
            # The purchaser, not the admin filing on their behalf.
            user_id=order.user_id,
            lemonsqueezy_order_id=order.lemonsqueezy_order_id,
            reason=body.reason,
            requested_amount=body.requested_amount,
            enforce_policy=False,
        )
    except RefundRequestError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    await db.commit()

    await audit_logger.log_refund_requested(
        user_id=order.user_id,
        refund_request_id=refund_request.id,
        order_id=order.lemonsqueezy_order_id,
        amount=refund_request.requested_amount,
        currency=refund_request.currency,
        reason=body.reason,
        requested_by_admin=True,
        admin_id=admin_user_id,
        db=db,
    )

    logger.info(
        f"Admin logged refund request {refund_request.id} for order {order.lemonsqueezy_order_id}",
        extra={
            "admin_user_id": str(admin_user_id),
            "user_id": str(order.user_id),
            "order_id": order.lemonsqueezy_order_id,
            "requested_amount": refund_request.requested_amount,
        },
    )

    return success(
        data=await _request_row_with_totals(db, await service.get(refund_request.id)),
        message="Refund request logged. Approve it, then process the refund.",
    )


@router.post(
    "/refunds/requests/{request_id}/approve",
    response_model=SuccessResponse[RefundRequestRow],
)
@require_permissions("billing.manage")
@db_transaction_handler("approve refund request")
async def approve_refund_request(
    request: Request,
    request_id: UUID,
    background_tasks: BackgroundTasks,
    body: RefundRequestReview = None,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Approve a refund request (super admin only). **No money moves.**

    Approval is a decision, not a payout. It records that the request is
    accepted and moves it to `approved`; issuing the refund is a separate,
    explicit action (`/refunds/requests/{id}/process`), so an admin can approve
    a queue of requests without any of them silently charging back.
    """
    admin_user_id = current_user.get("identity")
    await require_super_admin(db, admin_user_id)

    request_service = RefundRequestService(db)
    refund_request = await request_service.get(request_id)

    if not refund_request:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Refund request {request_id} not found",
        )

    if refund_request.status != RefundRequestStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Request has already been {refund_request.status.value}.",
        )

    await request_service.mark_reviewed(
        request=refund_request,
        admin_user_id=admin_user_id,
        status=RefundRequestStatus.APPROVED,
        admin_note=body.admin_note if body else None,
    )
    await db.commit()

    await audit_logger.log_refund_approved(
        admin_id=admin_user_id,
        user_id=refund_request.user_id,
        refund_request_id=refund_request.id,
        order_id=refund_request.lemonsqueezy_order_id,
        amount=refund_request.requested_amount or 0,
        currency=refund_request.currency or "USD",
        admin_note=body.admin_note if body else None,
        db=db,
    )

    amount_label = (
        f"{(refund_request.requested_amount or 0) / 100:.2f} {refund_request.currency or 'USD'}"
    )

    await _notify_requester(
        db=db,
        background_tasks=background_tasks,
        refund_request=refund_request,
        pref_flag="billing_refund_approved",
        message=f"Your refund of {amount_label} has been approved",
        email_method="send_refund_approved_email",
        email_kwargs={
            "user_id": refund_request.user_id,
            "product_name": (
                refund_request.order.product_name if refund_request.order else "Purchase"
            ),
            "refund_amount": amount_label,
            "order_id": refund_request.lemonsqueezy_order_id,
            "requested_date": refund_request.created_at.strftime("%B %d, %Y"),
            "admin_note": refund_request.admin_note,
        },
    )

    return success(
        data=await _request_row_with_totals(db, await request_service.get(request_id)),
        message="Refund request approved. Process it to issue the refund.",
    )


@router.post(
    "/refunds/requests/{request_id}/process",
    response_model=SuccessResponse[RefundRequestRow],
)
@require_permissions("billing.manage")
@db_transaction_handler("process refund request")
async def process_refund_request(
    request: Request,
    request_id: UUID,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Issue the refund for an already-approved request (super admin only).

    This is the step that moves money. It refunds the requested amount through
    LemonSqueezy, capped at what the order still has refundable, then links the
    resulting refund record to the request.

    A request that already has a refund linked is refused rather than paid
    twice, and a provider failure leaves the request `approved` so it can be
    retried without re-approving.
    """
    admin_user_id = current_user.get("identity")
    await require_super_admin(db, admin_user_id)

    request_service = RefundRequestService(db)
    refund_request = await request_service.get(request_id)

    if not refund_request:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Refund request {request_id} not found",
        )

    if refund_request.status != RefundRequestStatus.APPROVED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Only an approved request can be processed. This one is "
                f"{refund_request.status.value}."
            ),
        )

    if refund_request.refund_id is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This request has already been processed.",
        )

    order = refund_request.order

    try:
        refund_row, amounts = await _issue_refund(
            db,
            lemonsqueezy_order_id=refund_request.lemonsqueezy_order_id,
            user_id=refund_request.user_id,
            subscription_id=order.subscription_id if order else None,
            amount=refund_request.requested_amount,
            reason=f"Approved refund request: {(refund_request.reason or '')[:200]}",
        )
    except HTTPException:
        raise
    except (LemonSqueezyAPIError, LemonSqueezyError) as exc:
        # Left approved deliberately, so a provider outage does not consume the
        # request and the admin can simply try again.
        logger.error("Failed to refund via provider", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                "LemonSqueezy could not process this refund: "
                f"{getattr(exc, 'message', None) or str(exc)}"
            ),
        )

    # Link the request to the refund it produced, so the queue can tell an
    # approved request from a paid one. If LemonSqueezy reported no new money,
    # this order was already refunded to the same total, so the request is
    # linked to that existing refund rather than being left awaiting a payout
    # that will never come.
    if refund_row is None:
        existing = await db.execute(
            select(Refund)
            .where(
                Refund.lemonsqueezy_order_id == refund_request.lemonsqueezy_order_id,
                Refund.status != RefundStatus.FAILED,
            )
            .order_by(Refund.created_at.desc())
            .limit(1)
        )
        refund_row = existing.scalar_one_or_none()

    if refund_row is not None:
        refund_request.refund_id = refund_row.id
        await db.flush()

    await db.commit()

    # Only a refund that was actually written earns the email — a call that
    # recorded nothing new means the money had already gone back and the
    # customer has already been told.
    if refund_row is not None:
        background_tasks.add_task(
            send_billing_email_in_background,
            "send_refund_issued_email",
            user_id=refund_request.user_id,
            order_id=refund_request.lemonsqueezy_order_id,
            refund_amount=(
                f"{(refund_row.refund_amount or 0) / 100:.2f} {refund_row.currency or 'USD'}"
            ),
            refund_date=datetime.now(timezone.utc).strftime("%B %d, %Y"),
            original_plan_name=order.product_name if order else None,
        )

    client_ip = request.client.host if request.client else None
    await audit_logger.log_admin_refund_created(
        admin_id=admin_user_id if isinstance(admin_user_id, UUID) else UUID(str(admin_user_id)),
        user_id=refund_request.user_id,
        refund_id=refund_row.id if refund_row else None,
        subscription_id=order.subscription_id if order else None,
        amount=refund_row.refund_amount if refund_row else 0,
        reason=refund_request.reason,
        ip_address=client_ip,
        metadata={
            "refund_request_id": str(request_id),
            "lemonsqueezy_order_id": refund_request.lemonsqueezy_order_id,
            "order_total": amounts["total"],
            "refunded_amount": amounts["refunded_amount"],
            "refundable_amount": amounts["refundable_amount"],
            "is_partial": refund_row.is_partial if refund_row else False,
        },
        db=db,
    )

    return success(
        data=await _request_row_with_totals(db, await request_service.get(request_id)),
        message="Refund issued",
    )


@router.post(
    "/refunds/requests/{request_id}/unapprove",
    response_model=SuccessResponse[RefundRequestRow],
)
@require_permissions("billing.manage")
@db_transaction_handler("undo refund request approval")
async def unapprove_refund_request(
    request: Request,
    request_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Take back an approval without deciding against the request (super admin).

    Distinct from rejecting: this returns the request to `pending` as though it
    had never been reviewed, and the customer is told nothing. It is for an
    approval made in error — rejecting would tell them their refund was
    declined, which is a different thing to say.

    Only possible before the payout: once a refund exists there is nothing to
    take back.
    """
    admin_user_id = current_user.get("identity")
    await require_super_admin(db, admin_user_id)

    service = RefundRequestService(db)
    refund_request = await service.get(request_id)

    if not refund_request:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Refund request {request_id} not found",
        )

    if refund_request.refund_id is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This refund has already been paid out and cannot be un-approved.",
        )

    if refund_request.status != RefundRequestStatus.APPROVED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Only an approved request can be un-approved. This one is "
                f"{refund_request.status.value}."
            ),
        )

    # Only one request per order may be open at a time, enforced by a unique
    # index. Checked here so the clash comes back as an explanation rather than
    # a database error.
    clash = await db.execute(
        select(RefundRequest).where(
            RefundRequest.order_id == refund_request.order_id,
            RefundRequest.status == RefundRequestStatus.PENDING,
            RefundRequest.id != refund_request.id,
        )
    )
    if clash.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=("Another request for this order is already open. Resolve that one first."),
        )

    # Back to untouched: the review is undone, not recorded as a decision.
    refund_request.status = RefundRequestStatus.PENDING
    refund_request.reviewed_by_user_id = None
    refund_request.reviewed_at = None
    refund_request.admin_note = None
    refund_request.updated_at = datetime.now(timezone.utc)
    await db.flush()
    await db.commit()

    await audit_logger.log_refund_cancelled(
        admin_id=admin_user_id,
        user_id=refund_request.user_id,
        refund_request_id=refund_request.id,
        order_id=refund_request.lemonsqueezy_order_id,
        reason="Approval undone; reset to pending",
        db=db,
    )

    logger.info(
        f"Approval undone on refund request {request_id}; back to pending",
        extra={
            "request_id": str(request_id),
            "admin_user_id": str(admin_user_id),
            "lemonsqueezy_order_id": refund_request.lemonsqueezy_order_id,
        },
    )

    return success(
        data=await _request_row_with_totals(db, await service.get(request_id)),
        message="Approval undone. The request is pending again.",
    )


@router.post(
    "/refunds/requests/{request_id}/reject",
    response_model=SuccessResponse[RefundRequestRow],
)
@require_permissions("billing.manage")
@db_transaction_handler("reject refund request")
async def reject_refund_request(
    request: Request,
    request_id: UUID,
    background_tasks: BackgroundTasks,
    body: RefundRequestReview = None,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Reject a refund request (super admin only). No money moves.

    Works on an approved request as well as a pending one, so an approval can
    be taken back right up until it is processed — approving is a decision,
    and a decision that has cost nothing yet can be changed. What cannot be
    undone is a payout, so the guard is "has money moved" rather than "is it
    still pending".

    The note is shown to the customer, so it should explain the decision —
    especially when reversing an approval they have already been told about.
    """
    admin_user_id = current_user.get("identity")
    await require_super_admin(db, admin_user_id)

    service = RefundRequestService(db)
    refund_request = await service.get(request_id)

    if not refund_request:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Refund request {request_id} not found",
        )

    if refund_request.refund_id is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "This refund has already been paid out and cannot be rejected. "
                "Money that has been returned can only be recovered by the "
                "customer paying again."
            ),
        )

    if refund_request.status == RefundRequestStatus.REJECTED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Request has already been rejected.",
        )

    was_approved = refund_request.status == RefundRequestStatus.APPROVED

    await service.mark_reviewed(
        request=refund_request,
        admin_user_id=admin_user_id,
        status=RefundRequestStatus.REJECTED,
        admin_note=body.admin_note if body else None,
    )
    await db.commit()

    await audit_logger.log_refund_rejected(
        admin_id=admin_user_id,
        user_id=refund_request.user_id,
        refund_request_id=refund_request.id,
        order_id=refund_request.lemonsqueezy_order_id,
        reason=body.admin_note if body else None,
        db=db,
    )

    if was_approved:
        logger.info(
            f"Approval reversed on refund request {request_id} before payout",
            extra={
                "request_id": str(request_id),
                "admin_user_id": str(admin_user_id),
                "lemonsqueezy_order_id": refund_request.lemonsqueezy_order_id,
            },
        )

    amount_label = (
        f"{(refund_request.requested_amount or 0) / 100:.2f} {refund_request.currency or 'USD'}"
    )

    await _notify_requester(
        db=db,
        background_tasks=background_tasks,
        refund_request=refund_request,
        pref_flag="billing_refund_rejected",
        message=(
            "Your refund request was declined after review"
            if was_approved
            else "Your refund request was declined"
        ),
        email_method="send_refund_rejected_email",
        email_kwargs={
            "user_id": refund_request.user_id,
            "product_name": (
                refund_request.order.product_name if refund_request.order else "Purchase"
            ),
            "refund_amount": amount_label,
            "order_id": refund_request.lemonsqueezy_order_id,
            "requested_date": refund_request.created_at.strftime("%B %d, %Y"),
            "admin_note": refund_request.admin_note,
        },
    )

    return success(
        data=await _request_row_with_totals(db, await service.get(request_id)),
        message="Refund request rejected",
    )


@router.get("/refunds/{refund_id}", response_model=SuccessResponse[RefundAdminRow])
@require_permissions("billing.read")
@db_transaction_handler("get refund", auto_commit=False)
async def get_refund(
    request: Request,
    refund_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Get refund details by ID (super admin only).

    Path Parameters:
    - refund_id: UUID of the refund

    Returns:
    - Refund details with user and subscription information
    """
    admin_user_id = current_user.get("identity")
    await require_super_admin(db, admin_user_id)

    service = RefundService(db)
    refund = await service.get_refund(refund_id)

    if not refund:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Refund {refund_id} not found"
        )

    return success(data=refund, request=request, message="Refund retrieved successfully")


@router.post("/refunds/create", response_model=SuccessResponse[RefundCreateData])
@require_permissions("billing.manage")
@db_transaction_handler("create refund")
async def create_refund(
    request: Request,
    refund_request: RefundCreateRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Create a refund via LemonSqueezy API (super admin only).

    Request Body:
    - order_id: LemonSqueezy order ID (optional if subscription_id provided)
    - subscription_id: Subscription ID (optional if order_id provided)
    - amount: Refund amount in cents. Omit for a full refund, which returns
      the order's whole *remaining* balance — on an order that was already
      partially refunded that is less than its original total.
    - reason: Refund reason (optional)

    Returns:
    - Created refund details

    Note: Either order_id or subscription_id must be provided.

    An order can be refunded repeatedly while it still has a refundable
    balance; only a request that would take it past its total is refused.
    """
    admin_user_id = current_user.get("identity")
    await require_super_admin(db, admin_user_id)

    # Validate that at least one identifier is provided
    if not refund_request.order_id and not refund_request.subscription_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either order_id or subscription_id must be provided",
        )

    service = RefundService(db)

    # Get order_id from subscription if not provided
    lemonsqueezy_order_id = refund_request.order_id
    user_id = None
    subscription_id = refund_request.subscription_id

    if not lemonsqueezy_order_id and subscription_id:
        # Find subscription and get order_id
        stmt = select(UserSubscription).where(UserSubscription.id == subscription_id)
        result = await db.execute(stmt)
        subscription = result.scalar_one_or_none()

        if not subscription:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Subscription {subscription_id} not found",
            )

        if not subscription.lemonsqueezy_order_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Subscription does not have an associated order ID",
            )

        lemonsqueezy_order_id = subscription.lemonsqueezy_order_id
        user_id = subscription.user_id

    # If we still don't have user_id, resolve the order id against our records.
    # orders is checked first because it is the only table that holds *every*
    # LemonSqueezy order: licenses covers LTDs alone, and
    # user_subscriptions.lemonsqueezy_order_id is only populated on some rows.
    if not user_id:
        order_record = await OrderService(db).get_by_lemonsqueezy_id(lemonsqueezy_order_id)

        if order_record:
            user_id = order_record.user_id
            subscription_id = subscription_id or order_record.subscription_id
        else:
            license_stmt = select(License).where(
                License.lemonsqueezy_order_id == lemonsqueezy_order_id
            )
            license_result = await db.execute(license_stmt)
            license_record = license_result.scalar_one_or_none()

            if license_record:
                user_id = license_record.user_id
            else:
                # Try subscription by order_id
                sub_stmt = select(UserSubscription).where(
                    UserSubscription.lemonsqueezy_order_id == lemonsqueezy_order_id
                )
                sub_result = await db.execute(sub_stmt)
                subscription_record = sub_result.scalar_one_or_none()

                if subscription_record:
                    user_id = subscription_record.user_id
                    subscription_id = subscription_record.id
                else:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=(
                            f"No order, subscription or license found for order "
                            f"{lemonsqueezy_order_id}"
                        ),
                    )

    # Create refund via LemonSqueezy API. _issue_refund reads the order back
    # from LemonSqueezy first, so the refundable balance it validates against
    # is theirs and not our possibly-stale copy.
    try:
        refund, amounts = await _issue_refund(
            db,
            lemonsqueezy_order_id=lemonsqueezy_order_id,
            user_id=user_id,
            subscription_id=subscription_id,
            amount=refund_request.amount,
            reason=refund_request.reason,
        )

        if refund is None:
            # LemonSqueezy reported nothing new to record — the refund had
            # already been applied and we had already captured it.
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This refund has already been recorded.",
            )

        await db.commit()

        # An immediate refund skips the request queue, so this email is the
        # only thing that tells the customer their money is coming back.
        background_tasks.add_task(
            send_billing_email_in_background,
            "send_refund_issued_email",
            user_id=user_id,
            order_id=str(lemonsqueezy_order_id),
            refund_amount=(f"{(refund.refund_amount or 0) / 100:.2f} {refund.currency or 'USD'}"),
            refund_date=datetime.now(timezone.utc).strftime("%B %d, %Y"),
        )

        refund_details = await service.get_refund(refund.id)

        logger.info(
            f"Admin created refund for order {lemonsqueezy_order_id}",
            extra={
                "admin_user_id": str(admin_user_id),
                "refund_id": str(refund.id),
                "order_id": lemonsqueezy_order_id,
                "amount": refund.refund_amount,
            },
        )

        # Audit log
        client_ip = request.client.host if request.client else None
        await audit_logger.log_admin_refund_created(
            admin_id=admin_user_id if isinstance(admin_user_id, UUID) else UUID(str(admin_user_id)),
            user_id=user_id,
            refund_id=refund.id,
            subscription_id=subscription_id,
            amount=refund.refund_amount,
            reason=refund_request.reason,
            ip_address=client_ip,
            metadata={
                "lemonsqueezy_refund_id": refund.lemonsqueezy_refund_id,
                "lemonsqueezy_order_id": lemonsqueezy_order_id,
                "original_amount": amounts["total"],
                "refunded_amount": amounts["refunded_amount"],
                "refundable_amount": amounts["refundable_amount"],
                "is_partial": refund.is_partial,
            },
            db=db,
        )

        result_data = {
            "success": True,
            "refund": refund_details,
            "message": "Refund created successfully",
        }
        return success(data=result_data, request=request, message="Refund initiated successfully")

    except HTTPException:
        raise

    except LemonSqueezyTransientError as e:
        # 5xx / timeout / network from LemonSqueezy after retries were exhausted
        logger.error(
            f"LemonSqueezy temporarily unavailable while refunding order {lemonsqueezy_order_id}: {e}",
            exc_info=True,
            extra={"admin_user_id": str(admin_user_id)},
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="LemonSqueezy is temporarily unavailable. Please try again shortly.",
        )

    except (LemonSqueezyAPIError, LemonSqueezyError) as e:
        # LemonSqueezy rejected the request (expired/invalid API key, order not
        # found in this store, order not refundable, test/live mismatch, ...).
        # Surface the provider's own reason so the admin knows what to fix
        # instead of getting an opaque 500.
        ls_status = getattr(e, "status_code", None)
        ls_message = getattr(e, "message", None) or str(e)
        logger.error(
            f"LemonSqueezy rejected refund for order {lemonsqueezy_order_id}: "
            f"{ls_status} {ls_message}",
            exc_info=True,
            extra={"admin_user_id": str(admin_user_id), "ls_status_code": ls_status},
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"LemonSqueezy could not process this refund: {ls_message}",
        )

    except Exception:
        logger.error(
            f"Failed to create refund for order {lemonsqueezy_order_id}",
            exc_info=True,
            extra={"admin_user_id": str(admin_user_id)},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create refund. Please try again later.",
        )
