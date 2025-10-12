
"""
Subscription Plan API endpoints (Admin).

Routes delegate to SubscriptionPlanService to enforce thin controllers.
"""

from uuid import UUID
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.database.async_database import get_async_db
from src.api.security.dependencies import get_current_user
from src.api.schema.subscription import SubscriptionPlanCreate, SubscriptionPlanUpdate
from src.services.subscription_plan_service import SubscriptionPlanService
from src.utils.response_utils import created, success
from src.utils.route_decorators import db_transaction_handler


router = APIRouter(
    prefix="/subscriptions/plans",
    tags=["subscription-plans"],
)


@router.get("/public", response_model=dict)
@db_transaction_handler("list public plans", auto_commit=False)
async def list_public_plans(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
):
    """List public subscription plans (no authentication required)."""
    service = SubscriptionPlanService(db)

    # Only return active, public plans
    data = await service.list_plans(
        include_inactive=False,
        include_private=False,
        is_admin=False,
    )

    return success(
        data=data,
        request=request,
        message=f"Retrieved {data['count']} public subscription plan(s)",
    )


@router.post("", response_model=dict, status_code=status.HTTP_201_CREATED)
@db_transaction_handler("create plan", auto_commit=True)
async def create_plan(
    request: Request,
    plan_data: SubscriptionPlanCreate,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
):
    """Create a new subscription plan (admin only)."""
    service = SubscriptionPlanService(db)
    await service.require_admin(UUID(str(current_user.get("identity"))))

    result = await service.create_plan(plan_data)

    return created(
        data=result["plan"],
        request=request,
        message=result["message"],
    )


@router.get("", response_model=dict)
@db_transaction_handler("list plans", auto_commit=False)
async def list_plans(
    request: Request,
    include_inactive: bool = Query(False, description="Include inactive plans (admin only)"),
    include_private: bool = Query(False, description="Include private plans (admin only)"),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
):
    """List subscription plans with optional admin filters."""
    service = SubscriptionPlanService(db)
    is_admin = await service.is_admin(UUID(str(current_user.get("identity"))))

    data = await service.list_plans(
        include_inactive=include_inactive,
        include_private=include_private,
        is_admin=is_admin,
    )

    return success(
        data=data,
        request=request,
        message=f"Retrieved {data['count']} subscription plan(s)",
    )


@router.get("/{plan_id}", response_model=dict)
@db_transaction_handler("get plan", auto_commit=False)
async def get_plan(
    request: Request,
    plan_id: str,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
):
    """Retrieve subscription plan details."""
    service = SubscriptionPlanService(db)
    is_admin = await service.is_admin(UUID(str(current_user.get("identity"))))

    plan_data = await service.get_plan(UUID(plan_id), is_admin)

    return success(
        data=plan_data,
        request=request,
        message="Subscription plan retrieved successfully",
    )


@router.patch("/{plan_id}", response_model=dict)
@db_transaction_handler("update plan", auto_commit=True)
async def update_plan(
    request: Request,
    plan_id: str,
    plan_data: SubscriptionPlanUpdate,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
):
    """Update subscription plan metadata (admin only)."""
    service = SubscriptionPlanService(db)
    await service.require_admin(UUID(str(current_user.get("identity"))))

    updated_plan = await service.update_plan(UUID(plan_id), plan_data)

    return success(
        data=updated_plan,
        request=request,
        message=f"Subscription plan '{updated_plan['display_name']}' updated successfully",
    )


@router.delete("/{plan_id}", response_model=dict)
@db_transaction_handler("delete plan", auto_commit=True)
async def delete_plan(
    request: Request,
    plan_id: str,
    force: bool = Query(False, description="Force delete even if subscriptions exist"),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
):
    """Delete a subscription plan (admin only)."""
    service = SubscriptionPlanService(db)
    await service.require_admin(UUID(str(current_user.get("identity"))))

    result = await service.delete_plan(UUID(plan_id), force=force)

    return success(
        data=result,
        request=request,
        message=f"Subscription plan '{result['plan_name']}' deleted successfully",
    )
