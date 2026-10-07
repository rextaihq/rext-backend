"""
Subscription Plan API endpoints (Admin).

Routes delegate to SubscriptionPlanService to enforce thin controllers.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.database.async_database import get_async_db
from src.api.schema.response.plan_responses import (
    PlanCatalogResponse,
    PlanDeleteResponse,
    PlanDetails,
    PlanListResponse,
)
from src.api.schema.response_schemas import SuccessResponse
from src.api.schema.subscription import SubscriptionPlanCreate, SubscriptionPlanUpdate
from src.api.security.dependencies import get_current_user
from src.services.subscription_plan_service import SubscriptionPlanService
from src.utils.response_utils import created, success
from src.utils.route_decorators import db_transaction_handler, require_permissions

router = APIRouter(
    prefix="/subscriptions/plans",
    tags=["subscription-plans"],
)

# The public catalogue lives at /api/v1/plans, outside the admin prefix.
catalog_router = APIRouter(prefix="/plans", tags=["plans"])


@catalog_router.get("", response_model=SuccessResponse[PlanCatalogResponse])
@db_transaction_handler("get plan catalogue", auto_commit=False)
async def get_plan_catalog(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
):
    """
    The plans, the trial, the credit costs and the active offer (no authentication required).

    Public by design: the pricing pages show it to visitors who have not
    signed in. It holds only what those pages print.
    """
    data = await SubscriptionPlanService(db).get_catalog()

    return success(
        data=data,
        request=request,
        message=f"Retrieved {len(data['plans'])} plan(s)",
    )


@router.post("", response_model=SuccessResponse[PlanDetails], status_code=status.HTTP_201_CREATED)
@require_permissions("billing.manage", workspace_scoped=False)
@db_transaction_handler("create plan", auto_commit=True)
async def create_plan(
    request: Request,
    plan_data: SubscriptionPlanCreate,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
):
    """Create a new subscription plan. Requires billing.manage (SEC-RBAC-07)."""
    service = SubscriptionPlanService(db)

    result = await service.create_plan(plan_data)

    return created(
        data=result["plan"],
        request=request,
        message=result["message"],
    )


@router.get("", response_model=SuccessResponse[PlanListResponse])
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


@router.get("/{plan_id}", response_model=SuccessResponse[PlanDetails])
@require_permissions("billing.read", workspace_scoped=False)
@db_transaction_handler("get plan", auto_commit=False)
async def get_plan(
    request: Request,
    plan_id: UUID,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
):
    """Retrieve subscription plan details."""
    service = SubscriptionPlanService(db)
    is_admin = await service.is_admin(UUID(str(current_user.get("identity"))))

    plan_data = await service.get_plan(plan_id, is_admin)

    return success(
        data=plan_data,
        request=request,
        message="Subscription plan retrieved successfully",
    )


@router.patch("/{plan_id}", response_model=SuccessResponse[PlanDetails])
@require_permissions("billing.manage", workspace_scoped=False)
@db_transaction_handler("update plan", auto_commit=True)
async def update_plan(
    request: Request,
    plan_id: UUID,
    plan_data: SubscriptionPlanUpdate,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
):
    """Update subscription plan metadata (admin only)."""
    service = SubscriptionPlanService(db)
    await service.require_admin(UUID(str(current_user.get("identity"))))

    updated_plan = await service.update_plan(plan_id, plan_data)

    return success(
        data=updated_plan,
        request=request,
        message=f"Subscription plan '{updated_plan['display_name']}' updated successfully",
    )


@router.delete("/{plan_id}", response_model=SuccessResponse[PlanDeleteResponse])
@require_permissions("billing.manage", workspace_scoped=False)
@db_transaction_handler("delete plan", auto_commit=True)
async def delete_plan(
    request: Request,
    plan_id: UUID,
    force: bool = Query(False, description="Force delete even if subscriptions exist"),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
):
    """Delete a subscription plan (admin only)."""
    service = SubscriptionPlanService(db)
    await service.require_admin(UUID(str(current_user.get("identity"))))

    result = await service.delete_plan(plan_id, force=force)

    return success(
        data=result,
        request=request,
        message=f"Subscription plan '{result['plan_name']}' deleted successfully",
    )
