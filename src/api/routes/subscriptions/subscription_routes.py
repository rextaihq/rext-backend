"""
User Subscription API endpoints.

This module provides subscription management operations for end users.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from typing import List, Optional
from datetime import datetime, timedelta
import uuid

from src.api.database.async_database import get_async_db
from src.api.security.dependencies import get_current_user
from src.api.models.subscription_models.plans import SubscriptionPlan
from src.api.models.subscription_models.subscriptions import (
    UserSubscription,
    SubscriptionStatus,
    BillingPeriod
)
from src.api.models.workspace_models.workspace_model import WorkspaceModel as Workspace
from src.api.models.topic_models.topic_models import TopicsModel as Topic
from src.api.schema.subscription_schema import (
    SubscriptionCreateRequest,
    SubscriptionUpgradeRequest,
    SubscriptionCancelRequest,
    UserSubscriptionResponse,
    UsageStatsResponse,
    TrialStatusResponse
)
from src.utils.response_utils import success, error, created
from src.api.middleware.exceptions import (
    DuplicateResourceException,
    WrextValidationException,
    ResourceNotFoundException
)
from src.utils.logger import logger


router = APIRouter(
    prefix="/subscriptions",
    tags=["subscriptions"]
)


# Helper function to get active subscription
async def get_active_subscription(db: AsyncSession, user_id: str) -> Optional[UserSubscription]:
    """Get user's active subscription."""
    result = await db.execute(
        select(UserSubscription).where(
            UserSubscription.user_id == user_id,
            UserSubscription.status.in_([SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL])
        )
    )
    return result.scalar_one_or_none()


# Helper function to calculate usage counts
async def calculate_usage(db: AsyncSession, user_id: str) -> dict:
    """Calculate current resource usage for a user."""
    # Count workspaces owned by user
    workspaces_result = await db.execute(
        select(func.count(Workspace.id)).where(Workspace.creator_id == user_id)
    )
    workspaces_count = workspaces_result.scalar() or 0

    # Count topics across all user's workspaces
    topics_result = await db.execute(
        select(func.count(Topic.id)).join(Workspace).where(Workspace.creator_id == user_id)
    )
    topics_count = topics_result.scalar() or 0

    # TODO: Add knowledge items count when knowledge models are available
    knowledge_count = 0

    return {
        "workspaces": workspaces_count,
        "topics": topics_count,
        "knowledge_items": knowledge_count
    }


@router.post("/subscribe", response_model=dict, status_code=status.HTTP_201_CREATED)
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
    - Paid plans: Will integrate with Stripe (TODO: Task 5.4)

    Body:
    - plan_id: UUID of the subscription plan
    - billing_period: monthly or yearly

    Returns:
    - Created subscription details
    """
    try:
        user_id = current_user.get("identity")

        # Check if user already has an active subscription
        existing_subscription = await get_active_subscription(db, user_id)
        if existing_subscription:
            raise DuplicateResourceException(
                resource="subscription",
                identifier=user_id,
                message="User already has an active subscription. Use upgrade endpoint to change plans."
            )

        # Get the plan
        plan_result = await db.execute(
            select(SubscriptionPlan).where(
                SubscriptionPlan.id == subscription_data.plan_id,
                SubscriptionPlan.is_active == True
            )
        )
        plan = plan_result.scalar_one_or_none()

        if not plan:
            raise ResourceNotFoundException(
                resource="subscription_plan",
                identifier=subscription_data.plan_id
            )

        # Determine if this is a trial (first subscription gets 14 days trial for paid plans)
        is_trial = plan.price_monthly > 0 or plan.price_yearly > 0
        trial_days = 14 if is_trial else 0

        # Create subscription
        new_subscription = UserSubscription(
            id=uuid.uuid4(),
            user_id=user_id,
            plan_id=subscription_data.plan_id,
            status=SubscriptionStatus.TRIAL if is_trial else SubscriptionStatus.ACTIVE,
            billing_period=subscription_data.billing_period,
            start_date=datetime.utcnow(),
            trial_end_date=datetime.utcnow() + timedelta(days=trial_days) if is_trial else None,
            current_api_calls=0,
            usage_reset_date=datetime.utcnow() + timedelta(days=30),
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

        db.add(new_subscription)
        await db.commit()
        await db.refresh(new_subscription)

        logger.info(f"User {user_id} subscribed to plan: {plan.name} ({subscription_data.billing_period})")

        # Build response
        response_data = new_subscription.to_dict()
        response_data["plan_name"] = plan.name
        response_data["plan_display_name"] = plan.display_name

        return created(
            data=response_data,
            request=request,
            message=f"Successfully subscribed to {plan.display_name}"
        )

    except (DuplicateResourceException, ResourceNotFoundException, HTTPException):
        raise
    except Exception as e:
        logger.error(f"Error creating subscription: {e}")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create subscription"
        )


@router.get("/my-subscription", response_model=dict)
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
    try:
        user_id = current_user.get("identity")

        subscription = await get_active_subscription(db, user_id)

        if not subscription:
            return success(
                data=None,
                request=request,
                message="No active subscription found"
            )

        # Get plan details
        plan_result = await db.execute(
            select(SubscriptionPlan).where(SubscriptionPlan.id == subscription.plan_id)
        )
        plan = plan_result.scalar_one_or_none()

        # Build response
        response_data = subscription.to_dict()
        if plan:
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

    except Exception as e:
        logger.error(f"Error retrieving subscription: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve subscription"
        )


@router.get("/history", response_model=dict)
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
    try:
        user_id = current_user.get("identity")

        subscriptions_result = await db.execute(
            select(UserSubscription).where(
                UserSubscription.user_id == user_id
            ).order_by(UserSubscription.created_at.desc()).limit(limit)
        )
        subscriptions = subscriptions_result.scalars().all()

        subscriptions_data = []
        for sub in subscriptions:
            sub_data = sub.to_dict()
            # Add plan name
            plan_result = await db.execute(
                select(SubscriptionPlan).where(SubscriptionPlan.id == sub.plan_id)
            )
            plan = plan_result.scalar_one_or_none()
            if plan:
                sub_data["plan_name"] = plan.name
                sub_data["plan_display_name"] = plan.display_name
            subscriptions_data.append(sub_data)

        return success(
            data={
                "subscriptions": subscriptions_data,
                "count": len(subscriptions_data)
            },
            request=request,
            message=f"Retrieved {len(subscriptions_data)} subscription(s)"
        )

    except Exception as e:
        logger.error(f"Error retrieving subscription history: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve subscription history"
        )


@router.post("/upgrade", response_model=dict)
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
    try:
        user_id = current_user.get("identity")

        # Get current subscription
        current_subscription = await get_active_subscription(db, user_id)
        if not current_subscription:
            raise ResourceNotFoundException(
                resource="subscription",
                identifier=user_id,
                message="No active subscription found. Please subscribe first."
            )

        # Get current and new plans
        current_plan_result = await db.execute(
            select(SubscriptionPlan).where(SubscriptionPlan.id == current_subscription.plan_id)
        )
        current_plan = current_plan_result.scalar_one_or_none()

        new_plan_result = await db.execute(
            select(SubscriptionPlan).where(
                SubscriptionPlan.id == upgrade_data.new_plan_id,
                SubscriptionPlan.is_active == True
            )
        )
        new_plan = new_plan_result.scalar_one_or_none()

        if not new_plan:
            raise ResourceNotFoundException(
                resource="subscription_plan",
                identifier=upgrade_data.new_plan_id
            )

        # Check if it's the same plan
        if current_subscription.plan_id == upgrade_data.new_plan_id:
            # Only billing period change
            if upgrade_data.billing_period and upgrade_data.billing_period != current_subscription.billing_period:
                current_subscription.billing_period = upgrade_data.billing_period
                current_subscription.updated_at = datetime.utcnow()
                await db.commit()
                await db.refresh(current_subscription)

                return success(
                    data=current_subscription.to_dict(),
                    request=request,
                    message=f"Billing period updated to {upgrade_data.billing_period}"
                )
            else:
                raise WrextValidationException(
                    field="new_plan_id",
                    message="Already subscribed to this plan"
                )

        # Calculate current usage
        current_usage = await calculate_usage(db, user_id)

        # Validate downgrade (check if current usage exceeds new plan limits)
        is_downgrade = (
            (new_plan.price_monthly < current_plan.price_monthly if current_plan else False) or
            (new_plan.max_workspaces != -1 and new_plan.max_workspaces < current_usage["workspaces"]) or
            (new_plan.max_topics != -1 and new_plan.max_topics < current_usage["topics"]) or
            (new_plan.max_knowledge_items != -1 and new_plan.max_knowledge_items < current_usage["knowledge_items"])
        )

        if is_downgrade:
            # Check specific limits
            if new_plan.max_workspaces != -1 and current_usage["workspaces"] > new_plan.max_workspaces:
                raise WrextValidationException(
                    field="new_plan_id",
                    message=f"Cannot downgrade: You have {current_usage['workspaces']} workspaces, new plan allows {new_plan.max_workspaces}"
                )
            if new_plan.max_topics != -1 and current_usage["topics"] > new_plan.max_topics:
                raise WrextValidationException(
                    field="new_plan_id",
                    message=f"Cannot downgrade: You have {current_usage['topics']} topics, new plan allows {new_plan.max_topics}"
                )
            if new_plan.max_knowledge_items != -1 and current_usage["knowledge_items"] > new_plan.max_knowledge_items:
                raise WrextValidationException(
                    field="new_plan_id",
                    message=f"Cannot downgrade: You have {current_usage['knowledge_items']} knowledge items, new plan allows {new_plan.max_knowledge_items}"
                )

        # Update subscription
        current_subscription.plan_id = upgrade_data.new_plan_id
        if upgrade_data.billing_period:
            current_subscription.billing_period = upgrade_data.billing_period
        current_subscription.updated_at = datetime.utcnow()

        await db.commit()
        await db.refresh(current_subscription)

        action = "downgraded" if is_downgrade else "upgraded"
        logger.info(f"User {user_id} {action} subscription from {current_plan.name} to {new_plan.name}")

        # Build response
        response_data = current_subscription.to_dict()
        response_data["plan_name"] = new_plan.name
        response_data["plan_display_name"] = new_plan.display_name

        return success(
            data=response_data,
            request=request,
            message=f"Successfully {action} to {new_plan.display_name}"
        )

    except (ResourceNotFoundException, WrextValidationException, HTTPException):
        raise
    except Exception as e:
        logger.error(f"Error upgrading subscription: {e}")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to upgrade subscription"
        )


@router.post("/cancel", response_model=dict)
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
    try:
        user_id = current_user.get("identity")

        # Get current subscription
        subscription = await get_active_subscription(db, user_id)
        if not subscription:
            raise ResourceNotFoundException(
                resource="subscription",
                identifier=user_id,
                message="No active subscription found"
            )

        # Update subscription
        subscription.cancelled_at = datetime.utcnow()

        if cancel_data.cancel_immediately:
            subscription.status = SubscriptionStatus.CANCELLED
            subscription.end_date = datetime.utcnow()
        else:
            # Calculate end of billing period (30 days from start or last reset)
            if subscription.billing_period == BillingPeriod.MONTHLY:
                subscription.end_date = subscription.usage_reset_date
            elif subscription.billing_period == BillingPeriod.YEARLY:
                subscription.end_date = subscription.start_date + timedelta(days=365)
            else:  # LIFETIME
                subscription.end_date = None  # No end date for lifetime

        subscription.updated_at = datetime.utcnow()

        await db.commit()
        await db.refresh(subscription)

        logger.info(f"User {user_id} cancelled subscription (immediately={cancel_data.cancel_immediately})")
        if cancel_data.reason:
            logger.info(f"Cancellation reason: {cancel_data.reason}")

        message = "Subscription cancelled immediately" if cancel_data.cancel_immediately else f"Subscription will end on {subscription.end_date.strftime('%Y-%m-%d')}"

        return success(
            data=subscription.to_dict(),
            request=request,
            message=message
        )

    except (ResourceNotFoundException, HTTPException):
        raise
    except Exception as e:
        logger.error(f"Error cancelling subscription: {e}")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to cancel subscription"
        )


@router.get("/usage", response_model=dict)
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
    try:
        user_id = current_user.get("identity")

        # Get current subscription
        subscription = await get_active_subscription(db, user_id)
        if not subscription:
            raise ResourceNotFoundException(
                resource="subscription",
                identifier=user_id,
                message="No active subscription found"
            )

        # Get plan
        plan_result = await db.execute(
            select(SubscriptionPlan).where(SubscriptionPlan.id == subscription.plan_id)
        )
        plan = plan_result.scalar_one_or_none()

        if not plan:
            raise ResourceNotFoundException(
                resource="subscription_plan",
                identifier=subscription.plan_id
            )

        # Calculate current usage
        current_usage = await calculate_usage(db, user_id)

        # Helper function to calculate percentage
        def calc_percentage(current: int, maximum: int) -> float:
            if maximum == -1:  # Unlimited
                return 0.0
            if maximum == 0:
                return 100.0 if current > 0 else 0.0
            return round((current / maximum) * 100, 1)

        usage_data = {
            "subscription_id": str(subscription.id),
            "plan_name": plan.name,
            "billing_period": subscription.billing_period.value,
            "current_workspaces": current_usage["workspaces"],
            "current_topics": current_usage["topics"],
            "current_knowledge_items": current_usage["knowledge_items"],
            "current_api_calls": subscription.current_api_calls,
            "max_workspaces": plan.max_workspaces,
            "max_topics": plan.max_topics,
            "max_knowledge_items": plan.max_knowledge_items,
            "max_api_calls_per_month": plan.max_api_calls_per_month,
            "workspaces_usage_percent": calc_percentage(current_usage["workspaces"], plan.max_workspaces),
            "topics_usage_percent": calc_percentage(current_usage["topics"], plan.max_topics),
            "knowledge_items_usage_percent": calc_percentage(current_usage["knowledge_items"], plan.max_knowledge_items),
            "api_calls_usage_percent": calc_percentage(subscription.current_api_calls, plan.max_api_calls_per_month),
            "usage_reset_date": subscription.usage_reset_date.isoformat() if subscription.usage_reset_date else None
        }

        return success(
            data=usage_data,
            request=request,
            message="Usage statistics retrieved successfully"
        )

    except (ResourceNotFoundException, HTTPException):
        raise
    except Exception as e:
        logger.error(f"Error retrieving usage stats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve usage statistics"
        )


@router.get("/trial-status", response_model=dict)
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
    try:
        user_id = current_user.get("identity")

        subscription = await get_active_subscription(db, user_id)
        if not subscription:
            return success(
                data={
                    "is_trial": False,
                    "trial_end_date": None,
                    "days_remaining": None,
                    "trial_expired": False
                },
                request=request,
                message="No active subscription"
            )

        is_trial = subscription.status == SubscriptionStatus.TRIAL
        trial_end_date = subscription.trial_end_date
        days_remaining = None
        trial_expired = False

        if is_trial and trial_end_date:
            days_remaining = (trial_end_date - datetime.utcnow()).days
            trial_expired = days_remaining < 0

        trial_data = {
            "is_trial": is_trial,
            "trial_end_date": trial_end_date.isoformat() if trial_end_date else None,
            "days_remaining": max(0, days_remaining) if days_remaining is not None else None,
            "trial_expired": trial_expired
        }

        return success(
            data=trial_data,
            request=request,
            message="Trial status retrieved successfully"
        )

    except Exception as e:
        logger.error(f"Error retrieving trial status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve trial status"
        )
