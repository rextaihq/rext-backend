"""
Admin Subscription Management API endpoints.

This module provides administrative operations for subscription management,
including manual assignment, extensions, usage resets, and analytics.

All endpoints require super admin permissions.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_, case, extract
from typing import List, Optional, Dict
from datetime import datetime, timedelta
from decimal import Decimal
import uuid

from src.api.database.database import get_db
from src.api.security.dependencies import get_current_user
from src.api.models.subscription_models.plans import SubscriptionPlan
from src.api.models.subscription_models.subscriptions import (
    UserSubscription,
    SubscriptionStatus,
    BillingPeriod
)
from src.api.models.user_models.users import Users
from src.api.models.user_models.roles import Role
from src.api.models.user_models.user_roles import UserRole
from src.api.schema.subscription_schema import (
    AdminSubscriptionAssignRequest,
    AdminSubscriptionExtendRequest,
    AdminUsageResetRequest,
    UserSubscriptionResponse,
    SubscriptionStatsResponse,
    RevenueMetricsResponse,
    ChurnAnalysisResponse,
    TrialConversionResponse,
    PlanBreakdown
)
from src.utils.response_utils import success, error, created
from src.api.middleware.exceptions import (
    DuplicateResourceException,
    WrextValidationException,
    ResourceNotFoundException
)
from src.utils.logger import logger


router = APIRouter(
    prefix="/admin/subscriptions",
    tags=["admin-subscriptions"]
)


def check_super_admin(db: Session, user_id: str) -> bool:
    """Check if user is a super admin."""
    return db.query(UserRole).join(Role).filter(
        UserRole.user_id == user_id,
        Role.name == "super_admin"
    ).first() is not None


def require_super_admin(db: Session, user_id: str):
    """Raise exception if user is not super admin."""
    if not check_super_admin(db, user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Super admin role required for this operation"
        )


# ============================================================================
# ADMIN SUBSCRIPTION OVERRIDE ENDPOINTS
# ============================================================================

@router.post("/assign", response_model=dict, status_code=status.HTTP_201_CREATED)
def assign_subscription(
    request: Request,
    assign_data: AdminSubscriptionAssignRequest,
    db: Session = Depends(get_db),
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
        require_super_admin(db, admin_user_id)

        # Verify user exists
        user = db.query(Users).filter(Users.id == assign_data.user_id).first()
        if not user:
            raise ResourceNotFoundException(
                resource="user",
                identifier=assign_data.user_id
            )

        # Verify plan exists
        plan = db.query(SubscriptionPlan).filter(
            SubscriptionPlan.id == assign_data.plan_id,
            SubscriptionPlan.is_active == True
        ).first()
        if not plan:
            raise ResourceNotFoundException(
                resource="subscription_plan",
                identifier=assign_data.plan_id
            )

        # Check for existing active subscription
        existing = db.query(UserSubscription).filter(
            UserSubscription.user_id == assign_data.user_id,
            UserSubscription.status.in_([SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL])
        ).first()

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
        db.commit()
        db.refresh(new_subscription)

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
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to assign subscription"
        )


@router.post("/{subscription_id}/extend", response_model=dict)
def extend_subscription(
    request: Request,
    subscription_id: str,
    extend_data: AdminSubscriptionExtendRequest,
    db: Session = Depends(get_db),
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
        require_super_admin(db, admin_user_id)

        # Get subscription
        subscription = db.query(UserSubscription).filter(
            UserSubscription.id == subscription_id
        ).first()

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
        db.commit()
        db.refresh(subscription)

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
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to extend subscription"
        )


@router.post("/{subscription_id}/reset-usage", response_model=dict)
def reset_usage(
    request: Request,
    subscription_id: str,
    reset_data: AdminUsageResetRequest,
    db: Session = Depends(get_db),
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
        require_super_admin(db, admin_user_id)

        # Get subscription
        subscription = db.query(UserSubscription).filter(
            UserSubscription.id == subscription_id
        ).first()

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
        db.commit()
        db.refresh(subscription)

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
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to reset usage"
        )


@router.get("", response_model=dict)
def list_all_subscriptions(
    request: Request,
    status_filter: Optional[str] = Query(None, description="Filter by status (active, trial, cancelled, etc.)"),
    plan_id: Optional[str] = Query(None, description="Filter by plan ID"),
    user_email: Optional[str] = Query(None, description="Filter by user email"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
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
        require_super_admin(db, admin_user_id)

        # Build query
        query = db.query(UserSubscription, Users, SubscriptionPlan).join(
            Users, UserSubscription.user_id == Users.id
        ).join(
            SubscriptionPlan, UserSubscription.plan_id == SubscriptionPlan.id
        )

        # Apply filters
        if status_filter:
            try:
                status_enum = SubscriptionStatus(status_filter.lower())
                query = query.filter(UserSubscription.status == status_enum)
            except ValueError:
                raise WrextValidationException(
                    field="status_filter",
                    message=f"Invalid status: {status_filter}"
                )

        if plan_id:
            query = query.filter(UserSubscription.plan_id == plan_id)

        if user_email:
            query = query.filter(Users.email.ilike(f"%{user_email}%"))

        # Get total count
        total_count = query.count()

        # Apply pagination
        subscriptions = query.order_by(UserSubscription.created_at.desc()).offset(offset).limit(limit).all()

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
def get_subscription_admin(
    request: Request,
    subscription_id: str,
    db: Session = Depends(get_db),
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
        require_super_admin(db, admin_user_id)

        # Get subscription with related data
        result = db.query(UserSubscription, Users, SubscriptionPlan).join(
            Users, UserSubscription.user_id == Users.id
        ).join(
            SubscriptionPlan, UserSubscription.plan_id == SubscriptionPlan.id
        ).filter(
            UserSubscription.id == subscription_id
        ).first()

        if not result:
            raise ResourceNotFoundException(
                resource="subscription",
                identifier=subscription_id
            )

        subscription, user, plan = result

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


# ============================================================================
# ADMIN ANALYTICS ENDPOINTS
# ============================================================================

@router.get("/stats/overview", response_model=dict)
def get_subscription_stats(
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get overall subscription statistics (super admin only).

    Returns:
    - Total subscriptions by status
    - MRR (Monthly Recurring Revenue)
    - ARR (Annual Recurring Revenue)
    - Churn rate
    - Trial conversion rate
    - Customer lifetime value estimate
    """
    try:
        admin_user_id = current_user.get("identity")
        require_super_admin(db, admin_user_id)

        # Count subscriptions by status
        total_subscriptions = db.query(func.count(UserSubscription.id)).scalar() or 0

        active_subscriptions = db.query(func.count(UserSubscription.id)).filter(
            UserSubscription.status == SubscriptionStatus.ACTIVE
        ).scalar() or 0

        trial_subscriptions = db.query(func.count(UserSubscription.id)).filter(
            UserSubscription.status == SubscriptionStatus.TRIAL
        ).scalar() or 0

        cancelled_subscriptions = db.query(func.count(UserSubscription.id)).filter(
            UserSubscription.status == SubscriptionStatus.CANCELLED
        ).scalar() or 0

        expired_subscriptions = db.query(func.count(UserSubscription.id)).filter(
            UserSubscription.status == SubscriptionStatus.EXPIRED
        ).scalar() or 0

        suspended_subscriptions = db.query(func.count(UserSubscription.id)).filter(
            UserSubscription.status == SubscriptionStatus.SUSPENDED
        ).scalar() or 0

        # Calculate MRR (Monthly Recurring Revenue)
        mrr_result = db.query(
            func.sum(
                case(
                    (UserSubscription.billing_period == BillingPeriod.MONTHLY, SubscriptionPlan.price_monthly),
                    (UserSubscription.billing_period == BillingPeriod.YEARLY, SubscriptionPlan.price_yearly / 12),
                    else_=0
                )
            )
        ).join(
            SubscriptionPlan, UserSubscription.plan_id == SubscriptionPlan.id
        ).filter(
            UserSubscription.status.in_([SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL])
        ).scalar()

        mrr = float(mrr_result) if mrr_result else 0.0

        # Calculate ARR (Annual Recurring Revenue)
        arr = mrr * 12

        # Calculate churn rate (last 30 days)
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        cancellations_last_month = db.query(func.count(UserSubscription.id)).filter(
            UserSubscription.cancelled_at >= thirty_days_ago,
            UserSubscription.cancelled_at <= datetime.utcnow()
        ).scalar() or 0

        churn_rate = round(
            (cancellations_last_month / active_subscriptions * 100) if active_subscriptions > 0 else 0,
            2
        )

        # Calculate trial conversion rate (all time)
        total_trials_ever = db.query(func.count(UserSubscription.id)).filter(
            or_(
                UserSubscription.status == SubscriptionStatus.TRIAL,
                and_(
                    UserSubscription.status == SubscriptionStatus.ACTIVE,
                    UserSubscription.trial_end_date.isnot(None)
                )
            )
        ).scalar() or 0

        converted_trials = db.query(func.count(UserSubscription.id)).filter(
            UserSubscription.status == SubscriptionStatus.ACTIVE,
            UserSubscription.trial_end_date.isnot(None)
        ).scalar() or 0

        trial_conversion_rate = round(
            (converted_trials / total_trials_ever * 100) if total_trials_ever > 0 else 0,
            2
        )

        # Estimate average LTV (simplified: MRR * 12 months average retention)
        # This is a rough estimate - real LTV calculation requires historical data
        average_ltv = round(mrr * 12 if active_subscriptions > 0 else 0, 2)

        stats_data = {
            "total_subscriptions": total_subscriptions,
            "active_subscriptions": active_subscriptions,
            "trial_subscriptions": trial_subscriptions,
            "cancelled_subscriptions": cancelled_subscriptions,
            "expired_subscriptions": expired_subscriptions,
            "suspended_subscriptions": suspended_subscriptions,
            "mrr": round(mrr, 2),
            "arr": round(arr, 2),
            "churn_rate_monthly": churn_rate,
            "trial_conversion_rate": trial_conversion_rate,
            "average_ltv": average_ltv
        }

        return success(
            data=stats_data,
            request=request,
            message="Subscription statistics retrieved successfully"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving subscription stats: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve subscription statistics"
        )


@router.get("/stats/revenue", response_model=dict)
def get_revenue_metrics(
    request: Request,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get revenue metrics and breakdown (super admin only).

    Returns:
    - Current month revenue breakdown
    - Revenue by plan
    - Growth rate
    """
    try:
        admin_user_id = current_user.get("identity")
        require_super_admin(db, admin_user_id)

        # Calculate current month MRR
        current_mrr_result = db.query(
            func.sum(
                case(
                    (UserSubscription.billing_period == BillingPeriod.MONTHLY, SubscriptionPlan.price_monthly),
                    (UserSubscription.billing_period == BillingPeriod.YEARLY, SubscriptionPlan.price_yearly / 12),
                    else_=0
                )
            )
        ).join(
            SubscriptionPlan, UserSubscription.plan_id == SubscriptionPlan.id
        ).filter(
            UserSubscription.status.in_([SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL])
        ).scalar()

        current_mrr = float(current_mrr_result) if current_mrr_result else 0.0

        # Calculate new revenue (subscriptions started in last 30 days)
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        new_revenue_result = db.query(
            func.sum(
                case(
                    (UserSubscription.billing_period == BillingPeriod.MONTHLY, SubscriptionPlan.price_monthly),
                    (UserSubscription.billing_period == BillingPeriod.YEARLY, SubscriptionPlan.price_yearly / 12),
                    else_=0
                )
            )
        ).join(
            SubscriptionPlan, UserSubscription.plan_id == SubscriptionPlan.id
        ).filter(
            UserSubscription.start_date >= thirty_days_ago
        ).scalar()

        new_revenue = float(new_revenue_result) if new_revenue_result else 0.0

        # Get revenue breakdown by plan
        plan_revenue = db.query(
            SubscriptionPlan.id,
            SubscriptionPlan.name,
            SubscriptionPlan.display_name,
            func.count(UserSubscription.id).label('subscription_count'),
            func.sum(
                case(
                    (UserSubscription.billing_period == BillingPeriod.MONTHLY, SubscriptionPlan.price_monthly),
                    (UserSubscription.billing_period == BillingPeriod.YEARLY, SubscriptionPlan.price_yearly / 12),
                    else_=0
                )
            ).label('revenue_monthly')
        ).join(
            UserSubscription, SubscriptionPlan.id == UserSubscription.plan_id
        ).filter(
            UserSubscription.status.in_([SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL])
        ).group_by(
            SubscriptionPlan.id,
            SubscriptionPlan.name,
            SubscriptionPlan.display_name
        ).all()

        by_plan = []
        for plan_id, plan_name, display_name, count, revenue_monthly in plan_revenue:
            by_plan.append({
                "plan_id": str(plan_id),
                "plan_name": plan_name,
                "plan_display_name": display_name,
                "subscription_count": count,
                "revenue_monthly": round(float(revenue_monthly or 0), 2),
                "revenue_yearly": round(float(revenue_monthly or 0) * 12, 2)
            })

        # Simple growth rate calculation (would need historical data for accurate)
        growth_rate = round((new_revenue / current_mrr * 100) if current_mrr > 0 else 0, 2)

        revenue_data = {
            "current_month": {
                "mrr": round(current_mrr, 2),
                "new_revenue": round(new_revenue, 2),
                "expansion_revenue": 0.0,  # Placeholder - needs upgrade tracking
                "contraction_revenue": 0.0,  # Placeholder - needs downgrade tracking
                "churned_revenue": 0.0  # Placeholder - needs cancellation value tracking
            },
            "by_plan": by_plan,
            "growth_rate": growth_rate
        }

        return success(
            data=revenue_data,
            request=request,
            message="Revenue metrics retrieved successfully"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving revenue metrics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve revenue metrics"
        )


@router.get("/stats/churn", response_model=dict)
def get_churn_analysis(
    request: Request,
    period_days: int = Query(30, ge=1, le=365, description="Analysis period in days"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get churn analysis (super admin only).

    Query Parameters:
    - period_days: Analysis period (default 30 days)

    Returns:
    - Churn metrics for the specified period
    """
    try:
        admin_user_id = current_user.get("identity")
        require_super_admin(db, admin_user_id)

        period_start = datetime.utcnow() - timedelta(days=period_days)
        period_end = datetime.utcnow()

        # Active subscriptions at start of period
        total_active_start = db.query(func.count(UserSubscription.id)).filter(
            UserSubscription.start_date < period_start,
            or_(
                UserSubscription.end_date.is_(None),
                UserSubscription.end_date > period_start
            )
        ).scalar() or 0

        # New subscriptions in period
        new_subscriptions = db.query(func.count(UserSubscription.id)).filter(
            UserSubscription.start_date >= period_start,
            UserSubscription.start_date <= period_end
        ).scalar() or 0

        # Cancellations in period
        cancellations = db.query(func.count(UserSubscription.id)).filter(
            UserSubscription.cancelled_at >= period_start,
            UserSubscription.cancelled_at <= period_end
        ).scalar() or 0

        # Active subscriptions at end of period
        total_active_end = db.query(func.count(UserSubscription.id)).filter(
            UserSubscription.status.in_([SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL])
        ).scalar() or 0

        # Calculate rates
        churn_rate = round(
            (cancellations / total_active_start * 100) if total_active_start > 0 else 0,
            2
        )
        retention_rate = round(100 - churn_rate, 2)

        churn_data = {
            "period": f"last_{period_days}_days",
            "total_active_start": total_active_start,
            "new_subscriptions": new_subscriptions,
            "cancellations": cancellations,
            "total_active_end": total_active_end,
            "churn_rate": churn_rate,
            "retention_rate": retention_rate
        }

        return success(
            data=churn_data,
            request=request,
            message="Churn analysis retrieved successfully"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving churn analysis: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve churn analysis"
        )


@router.get("/stats/trial-conversion", response_model=dict)
def get_trial_conversion_metrics(
    request: Request,
    period_days: int = Query(90, ge=1, le=365, description="Analysis period in days"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get trial conversion metrics (super admin only).

    Query Parameters:
    - period_days: Analysis period (default 90 days)

    Returns:
    - Trial conversion statistics
    """
    try:
        admin_user_id = current_user.get("identity")
        require_super_admin(db, admin_user_id)

        period_start = datetime.utcnow() - timedelta(days=period_days)

        # Trials started in period
        total_trials_started = db.query(func.count(UserSubscription.id)).filter(
            UserSubscription.start_date >= period_start,
            UserSubscription.trial_end_date.isnot(None)
        ).scalar() or 0

        # Trials converted (now active with trial_end_date set)
        trials_converted = db.query(func.count(UserSubscription.id)).filter(
            UserSubscription.start_date >= period_start,
            UserSubscription.status == SubscriptionStatus.ACTIVE,
            UserSubscription.trial_end_date.isnot(None)
        ).scalar() or 0

        # Trials expired
        trials_expired = db.query(func.count(UserSubscription.id)).filter(
            UserSubscription.start_date >= period_start,
            UserSubscription.status == SubscriptionStatus.EXPIRED,
            UserSubscription.trial_end_date.isnot(None)
        ).scalar() or 0

        # Trials still active
        trials_active = db.query(func.count(UserSubscription.id)).filter(
            UserSubscription.start_date >= period_start,
            UserSubscription.status == SubscriptionStatus.TRIAL
        ).scalar() or 0

        # Calculate conversion rate
        conversion_rate = round(
            (trials_converted / total_trials_started * 100) if total_trials_started > 0 else 0,
            2
        )

        # Calculate average trial length
        trial_lengths = db.query(
            func.extract('epoch', UserSubscription.trial_end_date - UserSubscription.start_date) / 86400
        ).filter(
            UserSubscription.start_date >= period_start,
            UserSubscription.trial_end_date.isnot(None)
        ).all()

        avg_trial_length = round(
            sum(length[0] for length in trial_lengths if length[0]) / len(trial_lengths)
            if trial_lengths else 0,
            1
        )

        trial_data = {
            "total_trials_started": total_trials_started,
            "trials_converted": trials_converted,
            "trials_expired": trials_expired,
            "trials_active": trials_active,
            "conversion_rate": conversion_rate,
            "average_trial_length_days": avg_trial_length
        }

        return success(
            data=trial_data,
            request=request,
            message="Trial conversion metrics retrieved successfully"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving trial conversion metrics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve trial conversion metrics"
        )
