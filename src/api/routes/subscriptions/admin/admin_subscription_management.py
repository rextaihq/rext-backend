"""
Admin Subscription Management API endpoints.

This module provides administrative operations for subscription management,
including manual assignment, extensions, and usage resets.

All endpoints require super admin permissions.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timedelta
import uuid

from src.api.database.async_database import get_async_db
from src.api.security.dependencies import get_current_user
from src.api.models.subscription_models.plans import SubscriptionPlan
from src.api.models.subscription_models.subscriptions import (
    UserSubscription,
    SubscriptionStatus
)
from src.api.models.user_models.users import Users
from src.api.schema.subscription import (
    AdminSubscriptionAssignRequest,
    AdminSubscriptionExtendRequest,
    AdminUsageResetRequest
)
from src.utils.response_utils import success, created
from src.api.middleware.exceptions import (
    DuplicateResourceException,
    ResourceNotFoundException
)
from src.utils.logger import logger
from .shared.auth import require_super_admin


router = APIRouter()


# ============================================================================
# ADMIN SUBSCRIPTION OVERRIDE ENDPOINTS
# ============================================================================

@router.post("/assign", response_model=dict, status_code=status.HTTP_201_CREATED)
async def assign_subscription(
    request: Request,
    assign_data: AdminSubscriptionAssignRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Manually assign a subscription to a user (super admin only).

    Use cases:
    - Grant complimentary access to partners/influencers
    - Compensate users for service issues
    - Test subscription features with internal users

    Body:
    - user_id: UUID of the user
    - plan_id: UUID of the subscription plan
    - billing_period: monthly, yearly, or lifetime
    - status: active, trial, etc.
    - trial_days: Optional trial period

    Returns:
    - Created subscription details
    """
    try:
        admin_user_id = current_user.get("identity")
        await require_super_admin(db, admin_user_id)

        # Verify user exists
        result = await db.execute(select(Users).where(Users.id == assign_data.user_id))
        user = result.scalar_one_or_none()
        if not user:
            raise ResourceNotFoundException(
                resource="user",
                identifier=assign_data.user_id
            )

        # Verify plan exists
        result = await db.execute(
            select(SubscriptionPlan).where(
                SubscriptionPlan.id == assign_data.plan_id,
                SubscriptionPlan.is_active == True
            )
        )
        plan = result.scalar_one_or_none()
        if not plan:
            raise ResourceNotFoundException(
                resource="subscription_plan",
                identifier=assign_data.plan_id
            )

        # Check for existing active subscription
        result = await db.execute(
            select(UserSubscription).where(
                UserSubscription.user_id == assign_data.user_id,
                UserSubscription.status.in_([SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL])
            )
        )
        existing = result.scalar_one_or_none()

        if existing:
            raise DuplicateResourceException(
                resource="subscription",
                identifier=assign_data.user_id,
                message=f"User already has an active subscription (ID: {existing.id}). Cancel it first or use extend endpoint."
            )

        # Create subscription
        trial_end = None
        if assign_data.trial_days and assign_data.trial_days > 0:
            trial_end = datetime.utcnow() + timedelta(days=assign_data.trial_days)

        new_subscription = UserSubscription(
            id=uuid.uuid4(),
            user_id=assign_data.user_id,
            plan_id=assign_data.plan_id,
            status=assign_data.status,
            billing_period=assign_data.billing_period,
            start_date=datetime.utcnow(),
            trial_end_date=trial_end,
            current_api_calls=0,
            usage_reset_date=datetime.utcnow() + timedelta(days=30),
            subscription_metadata={"assigned_by_admin": admin_user_id},
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

        db.add(new_subscription)
        await db.commit()
        await db.refresh(new_subscription)

        logger.info(
            f"Admin {admin_user_id} assigned subscription: "
            f"user={assign_data.user_id}, plan={plan.name}, status={assign_data.status}"
        )

        # Build response
        response_data = new_subscription.to_dict()
        response_data["plan_name"] = plan.name
        response_data["plan_display_name"] = plan.display_name

        return created(
            data=response_data,
            request=request,
            message=f"Successfully assigned {plan.display_name} to user {user.username}"
        )

    except (ResourceNotFoundException, DuplicateResourceException, HTTPException):
        raise
    except Exception as e:
        logger.error(f"Error assigning subscription: {e}")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to assign subscription"
        )


@router.post("/{subscription_id}/extend", response_model=dict)
async def extend_subscription(
    request: Request,
    subscription_id: str,
    extend_data: AdminSubscriptionExtendRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Extend a subscription by specified days (super admin only).

    Use cases:
    - Compensate for service downtime
    - Extend trial period for sales opportunities
    - Grant additional time for migration/setup

    Body:
    - extend_days: Number of days to extend (1-3650)
    - reason: Required reason for extension

    Returns:
    - Updated subscription with new end date
    """
    try:
        admin_user_id = current_user.get("identity")
        await require_super_admin(db, admin_user_id)

        # Get subscription
        result = await db.execute(
            select(UserSubscription).where(UserSubscription.id == subscription_id)
        )
        subscription = result.scalar_one_or_none()

        if not subscription:
            raise ResourceNotFoundException(
                resource="subscription",
                identifier=subscription_id
            )

        # Calculate new end date
        if subscription.end_date:
            # Extend existing end date
            old_end = subscription.end_date
            subscription.end_date = subscription.end_date + timedelta(days=extend_data.extend_days)
        else:
            # No end date (lifetime or active) - set end date from now
            old_end = None
            subscription.end_date = datetime.utcnow() + timedelta(days=extend_data.extend_days)

        # If trial, extend trial end date
        if subscription.status == SubscriptionStatus.TRIAL and subscription.trial_end_date:
            subscription.trial_end_date = subscription.trial_end_date + timedelta(days=extend_data.extend_days)

        subscription.updated_at = datetime.utcnow()
        await db.commit()
        await db.refresh(subscription)

        logger.info(
            f"Admin {admin_user_id} extended subscription {subscription_id} by {extend_data.extend_days} days. "
            f"Reason: {extend_data.reason}"
        )

        return success(
            data=subscription.to_dict(),
            request=request,
            message=f"Subscription extended by {extend_data.extend_days} days"
        )

    except (ResourceNotFoundException, HTTPException):
        raise
    except Exception as e:
        logger.error(f"Error extending subscription {subscription_id}: {e}")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to extend subscription"
        )


@router.post("/{subscription_id}/reset-usage", response_model=dict)
async def reset_usage(
    request: Request,
    subscription_id: str,
    reset_data: AdminUsageResetRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Reset usage counters for a subscription (super admin only).

    Use cases:
    - Reset after testing/demo
    - Compensate for system errors
    - Grant additional quota mid-cycle

    Body:
    - reset_api_calls: Whether to reset API call counter
    - reason: Required reason for reset

    Returns:
    - Updated subscription with reset counters
    """
    try:
        admin_user_id = current_user.get("identity")
        await require_super_admin(db, admin_user_id)

        # Get subscription
        result = await db.execute(
            select(UserSubscription).where(UserSubscription.id == subscription_id)
        )
        subscription = result.scalar_one_or_none()

        if not subscription:
            raise ResourceNotFoundException(
                resource="subscription",
                identifier=subscription_id
            )

        old_api_calls = subscription.current_api_calls

        # Reset counters
        if reset_data.reset_api_calls:
            subscription.current_api_calls = 0
            subscription.usage_reset_date = datetime.utcnow() + timedelta(days=30)

        subscription.updated_at = datetime.utcnow()
        await db.commit()
        await db.refresh(subscription)

        logger.info(
            f"Admin {admin_user_id} reset usage for subscription {subscription_id}. "
            f"API calls: {old_api_calls} → 0. Reason: {reset_data.reason}"
        )

        return success(
            data=subscription.to_dict(),
            request=request,
            message="Usage counters reset successfully"
        )

    except (ResourceNotFoundException, HTTPException):
        raise
    except Exception as e:
        logger.error(f"Error resetting usage for subscription {subscription_id}: {e}")
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to reset usage"
        )
