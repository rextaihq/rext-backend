"""
User Subscription API endpoints.

This module provides subscription management operations for end users.
Routes handle HTTP concerns and delegate business logic to SubscriptionService.
"""

from fastapi import APIRouter, Depends, status, Request, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.database.async_database import get_async_db
from src.api.security.dependencies import get_current_user
from src.api.schema.subscription import (
    SubscriptionCreateRequest,
    SubscriptionUpgradeRequest,
    SubscriptionCancelRequest
)
from src.services.subscription_service import SubscriptionService
from src.utils.response_utils import success, created
from src.utils.route_decorators import db_transaction_handler, require_permissions


router = APIRouter(
    prefix="/subscriptions",
    tags=["subscriptions"]
)


@router.post("/subscribe", response_model=dict, status_code=status.HTTP_201_CREATED)
@db_transaction_handler("subscribe to plan")
@require_permissions("subscription.manage", workspace_scoped=False)
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

    return created(
        data=response_data,
        request=request,
        message=f"Successfully subscribed to {plan.display_name}"
    )


@router.get("/my-subscription", response_model=dict)
@db_transaction_handler("get my subscription", "Subscription retrieved successfully", auto_commit=False)
async def get_my_subscription(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get current user's active subscription.

    Returns:
    - Current subscription details with plan information
    - null if no active subscription
    """
    user_id = current_user.get("identity")
    service = SubscriptionService(db)

    subscription = await service.get_subscription_by_user(user_id)

    if not subscription:
        return success(
            data=None,
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

    return success(
        data=response_data,
        request=request,
        message="Subscription retrieved successfully"
    )


@router.get("/history", response_model=dict)
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


@router.post("/upgrade", response_model=dict)
@db_transaction_handler("upgrade subscription")
@require_permissions("subscription.manage", workspace_scoped=False)
async def upgrade_subscription(
    request: Request,
    upgrade_data: SubscriptionUpgradeRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Upgrade or downgrade subscription plan.

    Validates that current usage doesn't exceed new plan limits for downgrades.

    Body:
    - new_plan_id: UUID of the new plan
    - billing_period: (optional) Change billing period

    Returns:
    - Updated subscription details
    """
    user_id = current_user.get("identity")
    service = SubscriptionService(db)

    # Upgrade/downgrade subscription
    updated_subscription = await service.upgrade(
        user_id=user_id,
        new_plan_id=upgrade_data.new_plan_id,
        billing_period=upgrade_data.billing_period
    )

    # Get new plan details
    plan = await service.get_plan_by_id(upgrade_data.new_plan_id)

    # Build response
    response_data = updated_subscription.to_dict()
    response_data["plan_name"] = plan.name
    response_data["plan_display_name"] = plan.display_name

    return success(
        data=response_data,
        request=request,
        message=f"Successfully updated to {plan.display_name}"
    )


@router.post("/cancel", response_model=dict)
@db_transaction_handler("cancel subscription")
@require_permissions("subscription.manage", workspace_scoped=False)
async def cancel_subscription(
    request: Request,
    cancel_data: SubscriptionCancelRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Cancel current subscription.

    Body:
    - reason: (optional) Reason for cancellation
    - cancel_immediately: If true, cancel now. If false, cancel at end of billing period.

    Returns:
    - Updated subscription with cancellation details
    """
    user_id = current_user.get("identity")
    service = SubscriptionService(db)

    # Cancel subscription
    subscription = await service.cancel(
        user_id=user_id,
        reason=cancel_data.reason,
        cancel_immediately=cancel_data.cancel_immediately
    )

    message = (
        "Subscription cancelled immediately"
        if cancel_data.cancel_immediately
        else f"Subscription will end on {subscription.end_date.strftime('%Y-%m-%d') if subscription.end_date else 'N/A'}"
    )

    return success(
        data=subscription.to_dict(),
        request=request,
        message=message
    )


@router.get("/usage", response_model=dict)
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
    service = SubscriptionService(db)

    # Get current subscription
    subscription = await service.get_subscription_by_user(user_id)
    if not subscription:
        from src.api.middleware.exceptions import ResourceNotFoundException
        raise ResourceNotFoundException(
            resource_type="Subscription",
            resource_id=f"user:{user_id}",
            message="No active subscription found"
        )

    # Get plan
    plan = await service.get_plan_by_id(subscription.plan_id)

    # Calculate current usage
    current_usage = await service.calculate_usage(user_id)

    # Helper function to calculate percentage
    def calc_percentage(current: int, maximum: int) -> float:
        if maximum == -1:  # Unlimited
            return 0.0
        if maximum == 0:
            return 100.0 if current > 0 else 0.0
        return round((current / maximum) * 100, 1)

    usage_data = {
        "subscription_id": str(subscription.id),
        "plan_name": plan.name if plan else "Unknown",
        "billing_period": subscription.billing_period.value,
        "current_workspaces": current_usage["workspaces"],
        "current_topics": current_usage["topics"],
        "current_knowledge_items": current_usage["knowledge_items"],
        "current_api_calls": subscription.current_api_calls,
        "max_workspaces": plan.max_workspaces if plan else 0,
        "max_topics": plan.max_topics if plan else 0,
        "max_knowledge_items": plan.max_knowledge_items if plan else 0,
        "max_api_calls_per_month": plan.max_api_calls_per_month if plan else 0,
        "workspaces_usage_percent": calc_percentage(current_usage["workspaces"], plan.max_workspaces if plan else 0),
        "topics_usage_percent": calc_percentage(current_usage["topics"], plan.max_topics if plan else 0),
        "knowledge_items_usage_percent": calc_percentage(current_usage["knowledge_items"], plan.max_knowledge_items if plan else 0),
        "api_calls_usage_percent": calc_percentage(subscription.current_api_calls, plan.max_api_calls_per_month if plan else 0),
        "usage_reset_date": subscription.usage_reset_date.isoformat() if subscription.usage_reset_date else None
    }

    return success(
        data=usage_data,
        request=request,
        message="Usage statistics retrieved successfully"
    )


@router.get("/trial-status", response_model=dict)
@db_transaction_handler("get trial status", "Trial status retrieved successfully", auto_commit=False)
async def get_trial_status(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
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

    return success(
        data=trial_data,
        request=request,
        message="Trial status retrieved successfully"
    )
