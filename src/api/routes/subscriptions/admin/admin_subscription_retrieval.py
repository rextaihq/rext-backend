"""
Admin Subscription Retrieval API endpoints.

This module provides administrative operations for retrieving and listing
subscription information.

All endpoints require super admin permissions.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select
from typing import Optional

from src.api.database.async_database import get_async_db
from src.api.security.dependencies import get_current_user
from src.api.models.subscription_models.plans import SubscriptionPlan
from src.api.models.subscription_models.subscriptions import (
    UserSubscription,
    SubscriptionStatus
)
from src.api.models.user_models.users import Users
from src.utils.response_utils import success
from src.api.middleware.exceptions import (
    WrextValidationException,
    ResourceNotFoundException
)
from src.utils.logger import logger
from .shared.auth import require_super_admin


router = APIRouter()


@router.get("/", response_model=dict)
async def list_all_subscriptions(
    request: Request,
    status_filter: Optional[str] = Query(None, description="Filter by status (active, trial, cancelled, etc.)"),
    plan_id: Optional[str] = Query(None, description="Filter by plan ID"),
    user_email: Optional[str] = Query(None, description="Filter by user email"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    List all subscriptions with filters (super admin only).

    Query Parameters:
    - status_filter: Filter by status
    - plan_id: Filter by plan
    - user_email: Search by user email
    - limit: Results per page (max 500)
    - offset: Pagination offset

    Returns:
    - Paginated list of subscriptions with user and plan details
    """
    try:
        admin_user_id = current_user.get("identity")
        await require_super_admin(db, admin_user_id)

        # Build query
        query = select(UserSubscription, Users, SubscriptionPlan).join(
            Users, UserSubscription.user_id == Users.id
        ).join(
            SubscriptionPlan, UserSubscription.plan_id == SubscriptionPlan.id
        )

        # Apply filters
        if status_filter:
            try:
                status_enum = SubscriptionStatus(status_filter.lower())
                query = query.where(UserSubscription.status == status_enum)
            except ValueError:
                raise WrextValidationException(
                    field="status_filter",
                    message=f"Invalid status: {status_filter}"
                )

        if plan_id:
            query = query.where(UserSubscription.plan_id == plan_id)

        if user_email:
            query = query.where(Users.email.ilike(f"%{user_email}%"))

        # Get total count
        count_query = select(func.count()).select_from(query.subquery())
        result = await db.execute(count_query)
        total_count = result.scalar()

        # Apply pagination
        result = await db.execute(query.order_by(UserSubscription.created_at.desc()).offset(offset).limit(limit))
        subscriptions = result.all()

        # Format response
        subscriptions_data = []
        for subscription, user, plan in subscriptions:
            sub_data = subscription.to_dict()
            sub_data["user_email"] = user.email
            sub_data["user_username"] = user.username
            sub_data["plan_name"] = plan.name
            sub_data["plan_display_name"] = plan.display_name
            subscriptions_data.append(sub_data)

        return success(
            data={
                "subscriptions": subscriptions_data,
                "total": total_count,
                "limit": limit,
                "offset": offset,
                "has_more": (offset + limit) < total_count
            },
            request=request,
            message=f"Retrieved {len(subscriptions_data)} subscription(s)"
        )

    except (WrextValidationException, HTTPException):
        raise
    except Exception as e:
        logger.error(f"Error listing subscriptions: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list subscriptions"
        )


@router.get("/{subscription_id}", response_model=dict)
async def get_subscription_admin(
    request: Request,
    subscription_id: str,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get detailed subscription information (super admin only).

    Includes additional admin-only details:
    - User information
    - Payment details
    - Metadata
    - Audit trail

    Returns:
    - Complete subscription details
    """
    try:
        admin_user_id = current_user.get("identity")
        await require_super_admin(db, admin_user_id)

        # Get subscription with related data
        query = select(UserSubscription, Users, SubscriptionPlan).join(
            Users, UserSubscription.user_id == Users.id
        ).join(
            SubscriptionPlan, UserSubscription.plan_id == SubscriptionPlan.id
        ).where(
            UserSubscription.id == subscription_id
        )
        result = await db.execute(query)
        row = result.first()

        if not row:
            raise ResourceNotFoundException(
                resource="subscription",
                identifier=subscription_id
            )

        subscription, user, plan = row

        # Build detailed response
        response_data = subscription.to_dict()
        response_data["user"] = {
            "id": str(user.id),
            "email": user.email,
            "username": user.username,
            "status": user.status
        }
        response_data["plan"] = plan.to_dict()

        return success(
            data=response_data,
            request=request,
            message="Subscription details retrieved successfully"
        )

    except (ResourceNotFoundException, HTTPException):
        raise
    except Exception as e:
        logger.error(f"Error retrieving subscription {subscription_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve subscription"
        )
