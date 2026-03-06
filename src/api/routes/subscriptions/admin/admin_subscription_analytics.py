"""
Admin Subscription Analytics API endpoints.

This module provides administrative analytics operations for subscription
data including statistics, revenue metrics, churn analysis, and trial conversion.

All endpoints require super admin permissions.
"""

from fastapi import APIRouter, Depends, Request, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.database.async_database import get_async_db
from src.api.security.dependencies import get_current_user
from src.services.subscription_analytics_service import SubscriptionAnalyticsService
from src.utils.route_decorators import db_transaction_handler, require_permissions
from .shared.auth import require_super_admin


router = APIRouter()


# ============================================================================
# ADMIN ANALYTICS ENDPOINTS
# ============================================================================

@router.get("/stats/overview", response_model=dict)
@require_permissions("subscription.read", workspace_scoped=False)
@db_transaction_handler("get subscription stats", auto_commit=False)
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
    admin_user_id = current_user.get("identity")
    await require_super_admin(db, admin_user_id)

    service = SubscriptionAnalyticsService(db)
    return await service.get_subscription_stats()


@router.get("/stats/revenue", response_model=dict)
@require_permissions("subscription.read", workspace_scoped=False)
@db_transaction_handler("get revenue metrics", auto_commit=False)
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
    admin_user_id = current_user.get("identity")
    await require_super_admin(db, admin_user_id)

    service = SubscriptionAnalyticsService(db)
    return await service.get_revenue_metrics()


@router.get("/stats/churn", response_model=dict)
@require_permissions("subscription.read", workspace_scoped=False)
@db_transaction_handler("get churn analysis", auto_commit=False)
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
    admin_user_id = current_user.get("identity")
    await require_super_admin(db, admin_user_id)

    service = SubscriptionAnalyticsService(db)
    return await service.get_churn_analysis(period_days)


@router.get("/stats/trial-conversion", response_model=dict)
@require_permissions("subscription.read", workspace_scoped=False)
@db_transaction_handler("get trial conversion metrics", auto_commit=False)
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
    admin_user_id = current_user.get("identity")
    await require_super_admin(db, admin_user_id)

    service = SubscriptionAnalyticsService(db)
    return await service.get_trial_conversion_metrics(period_days)


@router.get("/analytics/overview", response_model=dict)
@require_permissions("subscription.read", workspace_scoped=False)
@db_transaction_handler("get analytics overview", auto_commit=False)
async def get_analytics_overview(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get comprehensive analytics overview (super admin only).

    Returns:
    - Subscription statistics (total, active, trial, MRR, ARR, churn, conversion)
    - Revenue by plan breakdown
    - Growth metrics (30-day new revenue, growth rate)
    - Recent subscriptions (last 10)
    """
    admin_user_id = current_user.get("identity")
    await require_super_admin(db, admin_user_id)

    service = SubscriptionAnalyticsService(db)
    return await service.get_analytics_overview()


@router.get("/analytics/revenue-history", response_model=dict)
@require_permissions("subscription.read", workspace_scoped=False)
@db_transaction_handler("get revenue history", auto_commit=False)
async def get_revenue_history(
    request: Request,
    period: str = Query("12_months", pattern="^(3_months|6_months|12_months)$", description="Time period"),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get historical revenue data for charts (super admin only).

    Query Parameters:
    - period: 3_months, 6_months, or 12_months (default 12_months)

    Returns:
    - Monthly revenue history with MRR, new revenue, churned revenue, net revenue
    """
    admin_user_id = current_user.get("identity")
    await require_super_admin(db, admin_user_id)

    service = SubscriptionAnalyticsService(db)
    return await service.get_revenue_history(period)


@router.get("/analytics/plan-distribution", response_model=dict)
@require_permissions("subscription.read", workspace_scoped=False)
@db_transaction_handler("get plan distribution", auto_commit=False)
async def get_plan_distribution(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get subscription distribution by plan (super admin only).

    Returns:
    - Plan breakdown with subscription counts, revenue, and percentages
    """
    admin_user_id = current_user.get("identity")
    await require_super_admin(db, admin_user_id)

    service = SubscriptionAnalyticsService(db)
    return await service.get_plan_distribution()


@router.get("/analytics/cohort-retention", response_model=dict)
@require_permissions("subscription.read", workspace_scoped=False)
@db_transaction_handler("get cohort retention", auto_commit=False)
async def get_cohort_retention(
    request: Request,
    cohort_months: int = Query(6, ge=1, le=12, description="Number of cohort months to analyze"),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get cohort retention analysis (super admin only).

    Query Parameters:
    - cohort_months: Number of cohorts to analyze (default 6, max 12)

    Returns:
    - Cohort retention matrix with month-over-month retention percentages
    """
    admin_user_id = current_user.get("identity")
    await require_super_admin(db, admin_user_id)

    service = SubscriptionAnalyticsService(db)
    return await service.get_cohort_retention(cohort_months)
