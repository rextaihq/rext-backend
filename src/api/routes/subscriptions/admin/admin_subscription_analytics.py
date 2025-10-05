"""
Admin Subscription Analytics API endpoints.

This module provides administrative analytics operations for subscription
data including statistics, revenue metrics, churn analysis, and trial conversion.

All endpoints require super admin permissions.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, and_, or_, case, select
from datetime import datetime, timedelta

from src.api.database.async_database import get_async_db
from src.api.security.dependencies import get_current_user
from src.api.models.subscription_models.plans import SubscriptionPlan
from src.api.models.subscription_models.subscriptions import (
    UserSubscription,
    SubscriptionStatus,
    BillingPeriod
)
from src.utils.response_utils import success
from src.utils.logger import logger
from .shared.auth import require_super_admin


router = APIRouter()


# ============================================================================
# ADMIN ANALYTICS ENDPOINTS
# ============================================================================

@router.get("/stats/overview", response_model=dict)
async def get_subscription_stats(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
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
        await require_super_admin(db, admin_user_id)

        # Count subscriptions by status
        result = await db.execute(select(func.count(UserSubscription.id)))
        total_subscriptions = result.scalar() or 0

        result = await db.execute(
            select(func.count(UserSubscription.id)).where(
                UserSubscription.status == SubscriptionStatus.ACTIVE
            )
        )
        active_subscriptions = result.scalar() or 0

        result = await db.execute(
            select(func.count(UserSubscription.id)).where(
                UserSubscription.status == SubscriptionStatus.TRIAL
            )
        )
        trial_subscriptions = result.scalar() or 0

        result = await db.execute(
            select(func.count(UserSubscription.id)).where(
                UserSubscription.status == SubscriptionStatus.CANCELLED
            )
        )
        cancelled_subscriptions = result.scalar() or 0

        result = await db.execute(
            select(func.count(UserSubscription.id)).where(
                UserSubscription.status == SubscriptionStatus.EXPIRED
            )
        )
        expired_subscriptions = result.scalar() or 0

        result = await db.execute(
            select(func.count(UserSubscription.id)).where(
                UserSubscription.status == SubscriptionStatus.SUSPENDED
            )
        )
        suspended_subscriptions = result.scalar() or 0

        # Calculate MRR (Monthly Recurring Revenue)
        mrr_query = select(
            func.sum(
                case(
                    (UserSubscription.billing_period == BillingPeriod.MONTHLY, SubscriptionPlan.price_monthly),
                    (UserSubscription.billing_period == BillingPeriod.YEARLY, SubscriptionPlan.price_yearly / 12),
                    else_=0
                )
            )
        ).join(
            SubscriptionPlan, UserSubscription.plan_id == SubscriptionPlan.id
        ).where(
            UserSubscription.status.in_([SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL])
        )
        result = await db.execute(mrr_query)
        mrr_result = result.scalar()

        mrr = float(mrr_result) if mrr_result else 0.0

        # Calculate ARR (Annual Recurring Revenue)
        arr = mrr * 12

        # Calculate churn rate (last 30 days)
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        result = await db.execute(
            select(func.count(UserSubscription.id)).where(
                UserSubscription.cancelled_at >= thirty_days_ago,
                UserSubscription.cancelled_at <= datetime.utcnow()
            )
        )
        cancellations_last_month = result.scalar() or 0

        churn_rate = round(
            (cancellations_last_month / active_subscriptions * 100) if active_subscriptions > 0 else 0,
            2
        )

        # Calculate trial conversion rate (all time)
        result = await db.execute(
            select(func.count(UserSubscription.id)).where(
                or_(
                    UserSubscription.status == SubscriptionStatus.TRIAL,
                    and_(
                        UserSubscription.status == SubscriptionStatus.ACTIVE,
                        UserSubscription.trial_end_date.isnot(None)
                    )
                )
            )
        )
        total_trials_ever = result.scalar() or 0

        result = await db.execute(
            select(func.count(UserSubscription.id)).where(
                UserSubscription.status == SubscriptionStatus.ACTIVE,
                UserSubscription.trial_end_date.isnot(None)
            )
        )
        converted_trials = result.scalar() or 0

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
async def get_revenue_metrics(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
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
        await require_super_admin(db, admin_user_id)

        # Calculate current month MRR
        current_mrr_query = select(
            func.sum(
                case(
                    (UserSubscription.billing_period == BillingPeriod.MONTHLY, SubscriptionPlan.price_monthly),
                    (UserSubscription.billing_period == BillingPeriod.YEARLY, SubscriptionPlan.price_yearly / 12),
                    else_=0
                )
            )
        ).join(
            SubscriptionPlan, UserSubscription.plan_id == SubscriptionPlan.id
        ).where(
            UserSubscription.status.in_([SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL])
        )
        result = await db.execute(current_mrr_query)
        current_mrr_result = result.scalar()

        current_mrr = float(current_mrr_result) if current_mrr_result else 0.0

        # Calculate new revenue (subscriptions started in last 30 days)
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        new_revenue_query = select(
            func.sum(
                case(
                    (UserSubscription.billing_period == BillingPeriod.MONTHLY, SubscriptionPlan.price_monthly),
                    (UserSubscription.billing_period == BillingPeriod.YEARLY, SubscriptionPlan.price_yearly / 12),
                    else_=0
                )
            )
        ).join(
            SubscriptionPlan, UserSubscription.plan_id == SubscriptionPlan.id
        ).where(
            UserSubscription.start_date >= thirty_days_ago
        )
        result = await db.execute(new_revenue_query)
        new_revenue_result = result.scalar()

        new_revenue = float(new_revenue_result) if new_revenue_result else 0.0

        # Get revenue breakdown by plan
        plan_revenue_query = select(
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
        ).where(
            UserSubscription.status.in_([SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL])
        ).group_by(
            SubscriptionPlan.id,
            SubscriptionPlan.name,
            SubscriptionPlan.display_name
        )
        result = await db.execute(plan_revenue_query)
        plan_revenue = result.all()

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
async def get_churn_analysis(
    request: Request,
    period_days: int = Query(30, ge=1, le=365, description="Analysis period in days"),
    db: AsyncSession = Depends(get_async_db),
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
        await require_super_admin(db, admin_user_id)

        period_start = datetime.utcnow() - timedelta(days=period_days)
        period_end = datetime.utcnow()

        # Active subscriptions at start of period
        result = await db.execute(
            select(func.count(UserSubscription.id)).where(
                UserSubscription.start_date < period_start,
                or_(
                    UserSubscription.end_date.is_(None),
                    UserSubscription.end_date > period_start
                )
            )
        )
        total_active_start = result.scalar() or 0

        # New subscriptions in period
        result = await db.execute(
            select(func.count(UserSubscription.id)).where(
                UserSubscription.start_date >= period_start,
                UserSubscription.start_date <= period_end
            )
        )
        new_subscriptions = result.scalar() or 0

        # Cancellations in period
        result = await db.execute(
            select(func.count(UserSubscription.id)).where(
                UserSubscription.cancelled_at >= period_start,
                UserSubscription.cancelled_at <= period_end
            )
        )
        cancellations = result.scalar() or 0

        # Active subscriptions at end of period
        result = await db.execute(
            select(func.count(UserSubscription.id)).where(
                UserSubscription.status.in_([SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL])
            )
        )
        total_active_end = result.scalar() or 0

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
async def get_trial_conversion_metrics(
    request: Request,
    period_days: int = Query(90, ge=1, le=365, description="Analysis period in days"),
    db: AsyncSession = Depends(get_async_db),
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
        await require_super_admin(db, admin_user_id)

        period_start = datetime.utcnow() - timedelta(days=period_days)

        # Trials started in period
        result = await db.execute(
            select(func.count(UserSubscription.id)).where(
                UserSubscription.start_date >= period_start,
                UserSubscription.trial_end_date.isnot(None)
            )
        )
        total_trials_started = result.scalar() or 0

        # Trials converted (now active with trial_end_date set)
        result = await db.execute(
            select(func.count(UserSubscription.id)).where(
                UserSubscription.start_date >= period_start,
                UserSubscription.status == SubscriptionStatus.ACTIVE,
                UserSubscription.trial_end_date.isnot(None)
            )
        )
        trials_converted = result.scalar() or 0

        # Trials expired
        result = await db.execute(
            select(func.count(UserSubscription.id)).where(
                UserSubscription.start_date >= period_start,
                UserSubscription.status == SubscriptionStatus.EXPIRED,
                UserSubscription.trial_end_date.isnot(None)
            )
        )
        trials_expired = result.scalar() or 0

        # Trials still active
        result = await db.execute(
            select(func.count(UserSubscription.id)).where(
                UserSubscription.start_date >= period_start,
                UserSubscription.status == SubscriptionStatus.TRIAL
            )
        )
        trials_active = result.scalar() or 0

        # Calculate conversion rate
        conversion_rate = round(
            (trials_converted / total_trials_started * 100) if total_trials_started > 0 else 0,
            2
        )

        # Calculate average trial length
        trial_lengths_query = select(
            func.extract('epoch', UserSubscription.trial_end_date - UserSubscription.start_date) / 86400
        ).where(
            UserSubscription.start_date >= period_start,
            UserSubscription.trial_end_date.isnot(None)
        )
        result = await db.execute(trial_lengths_query)
        trial_lengths = result.all()

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
