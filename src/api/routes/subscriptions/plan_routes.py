"""
Subscription Plan API endpoints (Admin).

This module provides CRUD operations for subscription plans with proper permission checks.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select
from typing import List, Optional
from datetime import datetime
import uuid

from src.api.database.async_database import get_async_db
from src.api.security.dependencies import get_current_user
from src.api.middleware.permissions import is_admin
from src.utils.route_decorators import require_permissions
from src.api.models.subscription_models.plans import SubscriptionPlan
from src.api.models.subscription_models.subscriptions import UserSubscription
from src.api.models.user_models.roles import Role
from src.api.models.user_models.user_roles import UserRole
from src.api.schema.subscription import (
    SubscriptionPlanCreate,
    SubscriptionPlanUpdate,
    SubscriptionPlanResponse
)
from src.utils.response_utils import success, error, created
from src.utils.db_utils import get_or_404
from src.api.middleware.exceptions import (
    DuplicateResourceException,
    WrextValidationException,
    ResourceNotFoundException,
    WrextAPIException
)
from src.utils.logger import logger
from src.utils.route_decorators import db_transaction_handler


router = APIRouter(
    prefix="/subscriptions/plans",
    tags=["subscription-plans"]
)


async def check_admin(db: AsyncSession, user_id: str) -> bool:
    """Check if user is an admin."""
    result = await db.execute(
        select(UserRole).join(Role).where(
            UserRole.user_id == user_id,
            Role.name.in_(["admin", "super_admin"])
        )
    )
    return result.scalar_one_or_none() is not None


@router.post("", response_model=dict, status_code=status.HTTP_201_CREATED)
@db_transaction_handler("create plan", auto_commit=True)
async def create_plan(
    request: Request,
    plan_data: SubscriptionPlanCreate,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Create a new subscription plan (admin only).

    Requires: Admin role

    Body:
    - name: Unique plan identifier (lowercase, no spaces)
    - display_name: Human-readable plan name
    - description: Plan description
    - price_monthly: Monthly price in USD
    - price_yearly: Yearly price in USD
    - features: Plan features as JSON
    - max_*: Resource limits

    Returns:
    - Created subscription plan
    """
    user_id = current_user.get("identity")

    # Check admin permission
    if not await check_admin(db, user_id):
        raise WrextAPIException(
            status_code=status.HTTP_403_FORBIDDEN,
            message="Admin role required to create subscription plans"
        )

    # Check if plan with same name already exists
    result = await db.execute(
        select(SubscriptionPlan).where(
            SubscriptionPlan.name == plan_data.name
        )
    )
    existing_plan = result.scalar_one_or_none()

    if existing_plan:
        raise DuplicateResourceException(
            resource="subscription_plan",
            identifier=plan_data.name,
            message=f"Plan with name '{plan_data.name}' already exists"
        )

    # Create new plan
    new_plan = SubscriptionPlan(
        id=uuid.uuid4(),
        name=plan_data.name,
        display_name=plan_data.display_name,
        description=plan_data.description,
        price_monthly=plan_data.price_monthly,
        price_yearly=plan_data.price_yearly,
        features=plan_data.features,
        max_workspaces=plan_data.max_workspaces,
        max_members_per_workspace=plan_data.max_members_per_workspace,
        max_topics=plan_data.max_topics,
        max_knowledge_items=plan_data.max_knowledge_items,
        max_api_calls_per_month=plan_data.max_api_calls_per_month,
        is_active=plan_data.is_active,
        is_public=plan_data.is_public,
        stripe_price_id_monthly=plan_data.stripe_price_id_monthly,
        stripe_price_id_yearly=plan_data.stripe_price_id_yearly,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )

    db.add(new_plan)
    await db.flush()
    await db.refresh(new_plan)

    logger.info(f"Admin {user_id} created subscription plan: {new_plan.name}")

    return {
        "data": new_plan.to_dict(),
        "message": f"Subscription plan '{plan_data.display_name}' created successfully",
        "status_code": status.HTTP_201_CREATED
    }


@router.get("", response_model=dict)
@db_transaction_handler("list plans", auto_commit=False)
async def list_plans(
    request: Request,
    include_inactive: bool = Query(False, description="Include inactive plans (admin only)"),
    include_private: bool = Query(False, description="Include private plans (admin only)"),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    List all subscription plans.

    Public endpoint - returns active, public plans by default.
    Admin users can see inactive and private plans.

    Query Parameters:
    - include_inactive: Show inactive plans (requires admin)
    - include_private: Show private plans (requires admin)

    Returns:
    - List of subscription plans sorted by price
    """
    user_id = current_user.get("identity")
    is_user_admin = await check_admin(db, user_id)

    # Build query
    query = select(SubscriptionPlan)

    # Apply filters based on user role
    if not is_user_admin:
        # Regular users see only active, public plans
        query = query.where(
            SubscriptionPlan.is_active == True,
            SubscriptionPlan.is_public == True
        )
    else:
        # Admin users can filter
        if not include_inactive:
            query = query.where(SubscriptionPlan.is_active == True)
        if not include_private:
            query = query.where(SubscriptionPlan.is_public == True)

    # Order by price (monthly)
    query = query.order_by(SubscriptionPlan.price_monthly.asc())
    result = await db.execute(query)
    plans = result.scalars().all()

    plans_data = [plan.to_dict() for plan in plans]

    return {
        "data": {
            "plans": plans_data,
            "count": len(plans_data)
        },
        "message": f"Retrieved {len(plans_data)} subscription plan(s)"
    }


@router.get("/{plan_id}", response_model=dict)
@db_transaction_handler("get plan", auto_commit=False)
async def get_plan(
    request: Request,
    plan_id: str,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get subscription plan details by ID.

    Returns:
    - Subscription plan details
    - Subscription count (admin only)
    """
    user_id = current_user.get("identity")
    is_user_admin = await check_admin(db, user_id)

    # Get plan
    plan = await get_or_404(db, SubscriptionPlan, plan_id, "subscription_plan")

    # Check visibility (non-admin can only see public, active plans)
    if not is_user_admin and (not plan.is_public or not plan.is_active):
        raise WrextAPIException(
            status_code=status.HTTP_404_NOT_FOUND,
            message="Subscription plan not found"
        )

    plan_data = plan.to_dict()

    # Add subscription count for admin users
    if is_user_admin:
        count_result = await db.execute(
            select(func.count(UserSubscription.id)).where(
                UserSubscription.plan_id == plan_id,
                UserSubscription.status.in_(["active", "trial"])
            )
        )
        active_subscriptions = count_result.scalar()

        plan_data["active_subscriptions"] = active_subscriptions or 0

    return {
        "data": plan_data,
        "message": "Subscription plan retrieved successfully"
    }


@router.patch("/{plan_id}", response_model=dict)
@db_transaction_handler("update plan", auto_commit=True)
async def update_plan(
    request: Request,
    plan_id: str,
    plan_data: SubscriptionPlanUpdate,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Update a subscription plan (admin only).

    Requires: Admin role

    Body:
    - Any fields from SubscriptionPlanUpdate (all optional)

    Returns:
    - Updated subscription plan
    """
    user_id = current_user.get("identity")

    # Check admin permission
    if not await check_admin(db, user_id):
        raise WrextAPIException(
            status_code=status.HTTP_403_FORBIDDEN,
            message="Admin role required to update subscription plans"
        )

    # Get plan
    plan = await get_or_404(db, SubscriptionPlan, plan_id, "subscription_plan")

    # Update fields (only if provided)
    update_data = plan_data.model_dump(exclude_unset=True)

    if not update_data:
        raise WrextValidationException(
            field="update_data",
            message="No fields provided for update"
        )

    for field, value in update_data.items():
        setattr(plan, field, value)

    plan.updated_at = datetime.utcnow()

    await db.flush()
    await db.refresh(plan)

    logger.info(f"Admin {user_id} updated subscription plan: {plan.name}")

    return {
        "data": plan.to_dict(),
        "message": f"Subscription plan '{plan.display_name}' updated successfully"
    }


@router.delete("/{plan_id}", response_model=dict)
@db_transaction_handler("delete plan", auto_commit=True)
@require_permissions("subscription.manage", workspace_scoped=False)
async def delete_plan(
    request: Request,
    plan_id: str,
    force: bool = Query(False, description="Force delete even if subscriptions exist"),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Delete a subscription plan (admin only).

    Requires: Admin role

    Query Parameters:
    - force: If true, delete even if active subscriptions exist (dangerous!)

    Note:
    - By default, cannot delete plans with active subscriptions
    - Use force=true only for testing/cleanup

    Returns:
    - Confirmation message
    """
    user_id = current_user.get("identity")

    # Check admin permission
    if not await check_admin(db, user_id):
        raise WrextAPIException(
            status_code=status.HTTP_403_FORBIDDEN,
            message="Admin role required to delete subscription plans"
        )

    # Get plan
    plan = await get_or_404(db, SubscriptionPlan, plan_id, "subscription_plan")

    # Check for active subscriptions
    count_result = await db.execute(
        select(func.count(UserSubscription.id)).where(
            UserSubscription.plan_id == plan_id,
            UserSubscription.status.in_(["active", "trial"])
        )
    )
    active_subscriptions = count_result.scalar()

    if active_subscriptions > 0 and not force:
        raise WrextValidationException(
            field="plan_id",
            message=f"Cannot delete plan with {active_subscriptions} active subscription(s). Use force=true to override."
        )

    plan_name = plan.display_name
    await db.delete(plan)
    await db.flush()

    logger.warning(f"Admin {user_id} deleted subscription plan: {plan.name} (force={force})")

    return {
        "data": {"deleted_plan_id": plan_id, "plan_name": plan_name},
        "message": f"Subscription plan '{plan_name}' deleted successfully"
    }
