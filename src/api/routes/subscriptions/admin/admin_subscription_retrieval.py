
"""
Admin Subscription Retrieval API endpoints.

This module provides administrative operations for retrieving and listing
subscription information.

All endpoints require super admin permissions.
"""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.database.async_database import get_async_db
from src.api.security.dependencies import get_current_user
from src.services.subscription_retrieval_service import SubscriptionRetrievalService
from src.utils.response_utils import success
from src.utils.route_decorators import db_transaction_handler, require_permissions

from .shared.auth import require_super_admin

router = APIRouter()


@router.get("/", response_model=dict)
@require_permissions("subscription.read", workspace_scoped=False)
@db_transaction_handler("list subscriptions", auto_commit=False)
async def list_all_subscriptions(
    request: Request,
    status_filter: Optional[str] = Query(None, description="Filter by status"),
    plan_id: Optional[UUID] = Query(None, description="Filter by plan ID"),
    user_email: Optional[str] = Query(None, description="Filter by user email"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
):
    admin_user_id = UUID(str(current_user.get("identity")))
    await require_super_admin(db, admin_user_id)

    service = SubscriptionRetrievalService(db)
    plan_uuid = plan_id
    result = await service.list_subscriptions(
        status_filter=status_filter,
        plan_id=plan_uuid,
        user_email=user_email,
        limit=limit,
        offset=offset,
    )
    return success(data=result["data"], request=request, message=result["message"])


@router.get("/{subscription_id}", response_model=dict)
@require_permissions("subscription.read", workspace_scoped=False)
@db_transaction_handler("get subscription", auto_commit=False)
async def get_subscription_admin(
    request: Request,
    subscription_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
):
    admin_user_id = UUID(str(current_user.get("identity")))
    await require_super_admin(db, admin_user_id)

    service = SubscriptionRetrievalService(db)
    result = await service.get_subscription(subscription_id=subscription_id)
    return success(data=result["data"], request=request, message=result["message"])