"""
Admin Refund Management API endpoints.

This module provides administrative operations for managing refunds including:
- Creating refunds via LemonSqueezy API
- Viewing refund history
- Tracking refund status

All endpoints require super admin permissions.
"""

from typing import Optional
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Query, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.api.database.async_database import get_async_db
from src.api.security.dependencies import get_current_user
from src.api.models.subscription_models.subscriptions import UserSubscription
from src.api.models.subscription_models.licenses import License
from src.api.models.subscription_models.refunds import RefundStatus
from src.api.schema.subscription.refund_schemas import (
    RefundCreateRequest,
    RefundCreateResponse,
)
from src.api.schema.response_schemas import SuccessResponse
from src.api.schema.response.refund_responses import (
    RefundAdminRow,
    RefundAdminListResponse,
    RefundCreateData,
    RefundResponse,
    RefundListResponse,
)
from src.services.refund_service import RefundService
from src.providers.payment.providers.lemonsqueezy import LemonSqueezyProvider
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

    # If we still don't have user_id, try to get it from license
    if not user_id:
        # Try to find license or subscription by order_id
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
                    detail=f"No subscription or license found for order {lemonsqueezy_order_id}"
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
        ls_refund = await provider.create_refund(
            order_id=lemonsqueezy_order_id,
            amount=refund_request.amount,
            reason=refund_request.reason
        )

        # Extract refund details from LemonSqueezy response
        ls_refund_id = ls_refund.get("id")
        ls_attributes = ls_refund.get("attributes", {})
        refund_amount = ls_attributes.get("amount") or refund_request.amount
        original_amount = ls_attributes.get("original_amount", refund_amount)

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

        # Mark as completed if LemonSqueezy says it's done
        if ls_attributes.get("status") == "completed":
            await service.mark_refund_completed(refund.id, ls_refund_id)

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
