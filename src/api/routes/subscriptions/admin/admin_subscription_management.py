
"""
Admin Subscription Management API endpoints.

This module provides administrative operations for subscription management,
including manual assignment, extensions, and usage resets.

All endpoints require super admin permissions.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.database.async_database import get_async_db
from src.api.security.dependencies import get_current_user


from src.api.schema.subscription import (
    AdminSubscriptionAssignRequest,
    AdminSubscriptionExtendRequest,
    AdminUsageResetRequest,
)
from src.services.subscription_management_service import SubscriptionManagementService
from src.utils.logger import logger
from src.utils.response_utils import success, created
from src.utils.route_decorators import db_transaction_handler, require_permissions
from .shared.auth import require_super_admin


router = APIRouter()


@router.post("/assign", response_model=dict, status_code=status.HTTP_201_CREATED)
@require_permissions("subscription.manage", workspace_scoped=False)
@db_transaction_handler("assign subscription", auto_commit=True)
async def assign_subscription(
    request: Request,
    assign_data: AdminSubscriptionAssignRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
):
    """Manually assign a subscription to a user (super admin only)."""
    admin_user_id = UUID(str(current_user.get("identity")))
    await require_super_admin(db, admin_user_id)

    service = SubscriptionManagementService(db)
    result = await service.assign_subscription(admin_user_id=admin_user_id, payload=assign_data)

    logger.info(
        "Subscription assignment completed",
        extra={"admin_user_id": str(admin_user_id), "target_user_id": str(assign_data.user_id)},
    )

    return created(
        data=result["subscription"],
        request=request,
        message=result["message"],
    )


@router.post("/{subscription_id}/extend", response_model=dict)
@require_permissions("subscription.manage", workspace_scoped=False)
@db_transaction_handler("extend subscription", auto_commit=True)
async def extend_subscription(
    request: Request,
    subscription_id: str,
    extend_data: AdminSubscriptionExtendRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
):
    """Extend a subscription by the specified number of days (super admin only)."""
    admin_user_id = UUID(str(current_user.get("identity")))
    await require_super_admin(db, admin_user_id)

    service = SubscriptionManagementService(db)
    result = await service.extend_subscription(
        admin_user_id=admin_user_id,
        subscription_id=UUID(subscription_id),
        payload=extend_data,
    )

    return success(
        data=result["subscription"],
        request=request,
        message=result["message"],
    )


@router.post("/{subscription_id}/reset-usage", response_model=dict)
@require_permissions("subscription.manage", workspace_scoped=False)
@db_transaction_handler("reset usage", auto_commit=True)
async def reset_usage(
    request: Request,
    subscription_id: str,
    reset_data: AdminUsageResetRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
):
    """Reset usage counters for a subscription (super admin only)."""
    admin_user_id = UUID(str(current_user.get("identity")))
    await require_super_admin(db, admin_user_id)

    service = SubscriptionManagementService(db)
    result = await service.reset_usage(
        admin_user_id=admin_user_id,
        subscription_id=UUID(subscription_id),
        payload=reset_data,
    )

    return success(
        data=result["subscription"],
        request=request,
        message=result["message"],
    )
