"""
Admin Refund Management API endpoints.

This module provides administrative operations for managing refunds including:
- Creating refunds via LemonSqueezy API
- Viewing refund history
- Tracking refund status

All endpoints require super admin permissions.
"""

from typing import Dict, Optional
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Request, Query, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import joinedload

from src.api.database.async_database import get_async_db
from src.api.security.dependencies import get_current_user
from src.api.models.subscription_models.subscriptions import UserSubscription
from src.api.models.subscription_models.licenses import License
from src.api.models.subscription_models.refunds import Refund, RefundStatus
from src.api.models.subscription_models.orders import Order, OrderStatus
from src.api.models.user_models.users import Users
from src.api.schema.subscription.refund_schemas import (
    RefundRequestReview,
    RefundCreateRequest,
    RefundCreateResponse,
)
from src.api.schema.response_schemas import SuccessResponse
from src.api.schema.response.refund_responses import (
    RefundableOrderListResponse,
    RefundRequestRow,
    RefundRequestListResponse,
    RefundAdminRow,
    RefundAdminListResponse,
    RefundCreateData,
    RefundResponse,
    RefundListResponse,
)
from src.services.refund_service import RefundService
from src.services.order_service import OrderService
from src.services.refund_request_service import RefundRequestService
from src.services.notification_helper import schedule_if_allowed
from src.api.models.subscription_models.refund_requests import RefundRequestStatus
from src.providers.payment.providers.lemonsqueezy import (
    LemonSqueezyProvider,
    LemonSqueezyError,
    LemonSqueezyAPIError,
    LemonSqueezyTransientError,
)
from src.utils.route_decorators import db_transaction_handler, require_permissions
from src.utils.response_utils import success
from src.utils.logger import logger
from src.services.audit_logger import audit_logger
from .shared.auth import require_super_admin
from src.api.config import settings
from src.config.payment_config import payment_settings


router = APIRouter()


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

async def get_lemonsqueezy_provider() -> LemonSqueezyProvider:
    """Get LemonSqueezy provider instance."""
    if not payment_settings.lemonsqueezy_api_key or not payment_settings.lemonsqueezy_store_id:
        raise HTTPException(status_code=503, detail="Payment provider is not configured")

    return LemonSqueezyProvider(
        api_key=payment_settings.lemonsqueezy_api_key,
        store_id=payment_settings.lemonsqueezy_store_id,
        webhook_secret=payment_settings.lemonsqueezy_webhook_secret,
        sandbox_mode=payment_settings.payment_sandbox_mode,
    )


# ============================================================================
# REFUND ENDPOINTS
# ============================================================================

@router.get("/refunds", response_model=SuccessResponse[RefundAdminListResponse])
@require_permissions("subscription.read")
@db_transaction_handler("list refunds", auto_commit=False)
async def list_refunds(
    request: Request,
    user_id: Optional[UUID] = Query(None, description="Filter by user ID"),
    subscription_id: Optional[UUID] = Query(None, description="Filter by subscription ID"),
    status: Optional[RefundStatus] = Query(None, description="Filter by status (pending/completed/failed)"),
    is_partial: Optional[bool] = Query(None, description="Filter by partial refund status"),
    start_date: Optional[datetime] = Query(None, description="Start date filter (ISO format)"),
    end_date: Optional[datetime] = Query(None, description="End date filter (ISO format)"),
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(50, ge=1, le=200, description="Items per page"),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
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

    return success(
        data=result,
        request=request,
        message="Refunds retrieved successfully"
    )


@router.get(
    "/refunds/orders",
    response_model=SuccessResponse[RefundableOrderListResponse],
)
@require_permissions("subscription.read")
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
        filters.append(
            or_(
                Order.lemonsqueezy_order_id.ilike(term),
                Order.product_name.ilike(term),
                Users.email.ilike(term),
                Users.full_name.ilike(term),
            )
        )

    if status_filter:
        filters.append(Order.status == status_filter.lower())
    else:
        # Only paid orders can be refunded; showing the rest is noise that
        # leads to a failed submit.
        filters.append(Order.status == OrderStatus.PAID)

    base = select(Order).join(Users, Users.id == Order.user_id)
    if filters:
        base = base.where(and_(*filters))

    count_result = await db.execute(
        select(func.count()).select_from(base.subquery())
    )
    total_items = count_result.scalar() or 0

    result = await db.execute(
        base.options(joinedload(Order.user))
        .order_by(Order.ordered_at.desc().nullslast(), Order.created_at.desc())
        .limit(per_page)
        .offset((page - 1) * per_page)
    )
    orders = result.unique().scalars().all()

    # One query for refunds across the page, rather than per row.
    order_ids = [o.lemonsqueezy_order_id for o in orders]
    refunded: Dict[str, int] = {}
    if order_ids:
        refund_rows = await db.execute(
            select(
                Refund.lemonsqueezy_order_id,
                func.coalesce(func.sum(Refund.refund_amount), 0),
            )
            .where(Refund.lemonsqueezy_order_id.in_(order_ids))
            .group_by(Refund.lemonsqueezy_order_id)
        )
        refunded = {row[0]: int(row[1] or 0) for row in refund_rows.all()}

    rows = [
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
            "already_refunded": order.lemonsqueezy_order_id in refunded,
            "refunded_amount": refunded.get(order.lemonsqueezy_order_id, 0),
        }
        for order in orders
    ]

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
    *, db, background_tasks, refund_request, pref_flag: str, message: str
) -> None:
    """Tell the customer the outcome. Best-effort.

    The decision is already committed, so a notification failure must not
    surface as an error on an action that actually succeeded.
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


def _admin_request_row(req) -> dict:
    """Serialise a refund request with the context an admin needs to judge it."""
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
        "order_total": req.order.total if req.order else None,
    }


@router.get(
    "/refunds/requests",
    response_model=SuccessResponse[RefundRequestListResponse],
)
@require_permissions("subscription.read")
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

    return success(
        data={
            "data": [_admin_request_row(r) for r in result["requests"]],
            "pagination": result["pagination"],
        },
        message="Refund requests retrieved successfully",
    )


@router.post(
    "/refunds/requests/{request_id}/approve",
    response_model=SuccessResponse[RefundRequestRow],
)
@require_permissions("subscription.manage")
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
    Approve a refund request and refund the order (super admin only).

    Approval and refund are one step: the refund is issued against the order
    the request names, then the request is marked approved and linked to the
    resulting refund record. If the payment provider rejects the refund, the
    request stays pending so it can be retried.
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

    refund_service = RefundService(db)

    if await refund_service.get_refund_by_order_id(
        refund_request.lemonsqueezy_order_id
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This order has already been refunded.",
        )

    try:
        provider = await get_lemonsqueezy_provider()
        ls_refund = await provider.create_refund(
            order_id=refund_request.lemonsqueezy_order_id,
            amount=refund_request.requested_amount,
            reason=f"Approved refund request: {refund_request.reason[:200]}",
        )
    except Exception:
        # Left pending deliberately, so a provider outage does not consume the
        # request and the admin can simply try again.
        logger.error("Failed to refund via provider", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The payment provider rejected the refund. The request is still pending.",
        )

    ls_attributes = ls_refund.get("attributes", {})
    refund = await refund_service.create_refund_record(
        user_id=refund_request.user_id,
        lemonsqueezy_order_id=refund_request.lemonsqueezy_order_id,
        refund_amount=ls_attributes.get("amount") or refund_request.requested_amount,
        original_amount=refund_request.requested_amount,
        lemonsqueezy_refund_id=ls_refund.get("id"),
        reason=refund_request.reason,
    )
    await refund_service.mark_refund_completed(refund.id, ls_refund.get("id"))

    await request_service.mark_reviewed(
        request=refund_request,
        admin_user_id=admin_user_id,
        status=RefundRequestStatus.APPROVED,
        admin_note=body.admin_note if body else None,
        refund_id=refund.id,
    )
    await db.commit()

    await _notify_requester(
        db=db,
        background_tasks=background_tasks,
        refund_request=refund_request,
        pref_flag="billing_refund_approved",
        message=(
            f"Your refund of {(refund_request.requested_amount or 0) / 100:.2f} "
            f"{refund_request.currency} has been approved"
        ),
    )

    return success(
        data=_admin_request_row(await request_service.get(request_id)),
        message="Refund request approved and refund issued",
    )


@router.post(
    "/refunds/requests/{request_id}/reject",
    response_model=SuccessResponse[RefundRequestRow],
)
@require_permissions("subscription.manage")
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

    The note is shown to the customer, so it should explain the decision.
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

    if refund_request.status != RefundRequestStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Request has already been {refund_request.status.value}.",
        )

    await service.mark_reviewed(
        request=refund_request,
        admin_user_id=admin_user_id,
        status=RefundRequestStatus.REJECTED,
        admin_note=body.admin_note if body else None,
    )
    await db.commit()

    await _notify_requester(
        db=db,
        background_tasks=background_tasks,
        refund_request=refund_request,
        pref_flag="billing_refund_rejected",
        message="Your refund request was declined",
    )

    return success(
        data=_admin_request_row(await service.get(request_id)),
        message="Refund request rejected",
    )


@router.get("/refunds/{refund_id}", response_model=SuccessResponse[RefundAdminRow])
@require_permissions("subscription.read")
@db_transaction_handler("get refund", auto_commit=False)
async def get_refund(
    request: Request,
    refund_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
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
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Refund {refund_id} not found"
        )

    return success(
        data=refund,
        request=request,
        message="Refund retrieved successfully"
    )


@router.post("/refunds/create", response_model=SuccessResponse[RefundCreateData])
@require_permissions("subscription.manage")
@db_transaction_handler("create refund")
async def create_refund(
    request: Request,
    refund_request: RefundCreateRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Create a refund via LemonSqueezy API (super admin only).

    Request Body:
    - order_id: LemonSqueezy order ID (optional if subscription_id provided)
    - subscription_id: Subscription ID (optional if order_id provided)
    - amount: Refund amount in cents (optional, defaults to full refund)
    - reason: Refund reason (optional)

    Returns:
    - Created refund details

    Note: Either order_id or subscription_id must be provided.
    """
    admin_user_id = current_user.get("identity")
    await require_super_admin(db, admin_user_id)

    # Validate that at least one identifier is provided
    if not refund_request.order_id and not refund_request.subscription_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either order_id or subscription_id must be provided"
        )

    service = RefundService(db)

    # Get order_id from subscription if not provided
    lemonsqueezy_order_id = refund_request.order_id
    user_id = None
    subscription_id = refund_request.subscription_id
    original_amount = 0

    if not lemonsqueezy_order_id and subscription_id:
        # Find subscription and get order_id
        stmt = select(UserSubscription).where(UserSubscription.id == subscription_id)
        result = await db.execute(stmt)
        subscription = result.scalar_one_or_none()

        if not subscription:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Subscription {subscription_id} not found"
            )

        if not subscription.lemonsqueezy_order_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Subscription does not have an associated order ID"
            )

        lemonsqueezy_order_id = subscription.lemonsqueezy_order_id
        user_id = subscription.user_id

    # If we still don't have user_id, resolve the order id against our records.
    # orders is checked first because it is the only table that holds *every*
    # LemonSqueezy order: licenses covers LTDs alone, and
    # user_subscriptions.lemonsqueezy_order_id is only populated on some rows.
    if not user_id:
        order_record = await OrderService(db).get_by_lemonsqueezy_id(
            lemonsqueezy_order_id
        )

        if order_record:
            user_id = order_record.user_id
            subscription_id = subscription_id or order_record.subscription_id
            original_amount = order_record.total or 0
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
                        )
                    )

    # Check if refund already exists
    existing_refund = await service.get_refund_by_order_id(lemonsqueezy_order_id)
    if existing_refund:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Refund already exists for order {lemonsqueezy_order_id}"
        )

    # Create refund via LemonSqueezy API
    try:
        provider = await get_lemonsqueezy_provider()
        ls_order = await provider.create_refund(
            order_id=lemonsqueezy_order_id,
            amount=refund_request.amount,
            reason=refund_request.reason
        )

        # Extract order details from LemonSqueezy response
        ls_attributes = ls_order.get("attributes", {})
        ls_refund_id = f"ref_{lemonsqueezy_order_id}"
        refund_amount = (
            ls_attributes.get("refunded_amount")
            or refund_request.amount
            or original_amount
        )
        if not original_amount:
            original_amount = ls_attributes.get("total") or refund_amount

        # Create refund record in database
        refund = await service.create_refund_record(
            user_id=user_id,
            lemonsqueezy_order_id=lemonsqueezy_order_id,
            refund_amount=refund_amount,
            original_amount=original_amount,
            subscription_id=subscription_id,
            lemonsqueezy_refund_id=ls_refund_id,
            reason=refund_request.reason,
        )

        # Mark refund as completed
        await service.mark_refund_completed(refund.id, ls_refund_id)

        # Also update local order status to refunded
        order_record = await OrderService(db).get_by_lemonsqueezy_id(lemonsqueezy_order_id)
        if order_record:
            order_record.status = OrderStatus.REFUNDED
            order_record.refunded_at = datetime.now(timezone.utc)
            await db.flush()

        await db.commit()

        # Get full refund details
        refund_details = await service.get_refund(refund.id)

        logger.info(
            f"Admin created refund for order {lemonsqueezy_order_id}",
            extra={
                "admin_user_id": str(admin_user_id),
                "refund_id": str(refund.id),
                "order_id": lemonsqueezy_order_id,
                "amount": refund_amount
            }
        )

        # Audit log
        client_ip = request.client.host if request.client else None
        audit_logger.log_admin_refund_created(
            admin_id=admin_user_id if isinstance(admin_user_id, UUID) else UUID(str(admin_user_id)),
            user_id=user_id,
            refund_id=refund.id,
            subscription_id=subscription_id,
            amount=refund_amount,
            reason=refund_request.reason,
            ip_address=client_ip,
            metadata={
                "lemonsqueezy_refund_id": ls_refund_id,
                "lemonsqueezy_order_id": lemonsqueezy_order_id,
                "original_amount": original_amount,
                "is_partial": refund_amount < original_amount if original_amount > 0 else False,
            }
        )

        result_data = {
            "success": True,
            "refund": refund_details,
            "message": "Refund created successfully"
        }
        return success(
            data=result_data,
            request=request,
            message="Refund initiated successfully"
        )

    except HTTPException:
        raise

    except LemonSqueezyTransientError as e:
        # 5xx / timeout / network from LemonSqueezy after retries were exhausted
        logger.error(
            f"LemonSqueezy temporarily unavailable while refunding order {lemonsqueezy_order_id}: {e}",
            exc_info=True,
            extra={"admin_user_id": str(admin_user_id)}
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="LemonSqueezy is temporarily unavailable. Please try again shortly."
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
            extra={"admin_user_id": str(admin_user_id), "ls_status_code": ls_status}
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"LemonSqueezy could not process this refund: {ls_message}"
        )

    except Exception as e:
        logger.error(
            f"Failed to create refund for order {lemonsqueezy_order_id}",
            exc_info=True,
            extra={"admin_user_id": str(admin_user_id)}
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create refund. Please try again later."
        )
