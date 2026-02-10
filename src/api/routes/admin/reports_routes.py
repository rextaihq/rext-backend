"""
Admin Reports API endpoints.

This module provides administrative reporting operations
including revenue reports and data exports.

All endpoints require admin permissions.
"""

from datetime import datetime, timedelta
from typing import Optional
import csv
from io import StringIO

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.database.async_database import get_async_db
from src.api.security.dependencies import get_current_user
from src.services.subscription_analytics_service import SubscriptionAnalyticsService
from src.utils.route_decorators import db_transaction_handler, require_permissions


router = APIRouter(prefix="/reports", tags=["Admin - Reports"])


# ============================================================================
# REVENUE REPORTS
# ============================================================================


@router.get("/revenue", response_model=dict)
@require_permissions("audit.read", workspace_scoped=False)
@db_transaction_handler("get revenue report", auto_commit=False)
async def get_revenue_report(
    request: Request,
    start_date: Optional[datetime] = Query(None, description="Start date (ISO format)"),
    end_date: Optional[datetime] = Query(None, description="End date (ISO format)"),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get comprehensive revenue report for date range (admin only).

    Query Parameters:
    - start_date: Start date (defaults to 30 days ago)
    - end_date: End date (defaults to today)

    Returns:
    - Revenue summary (MRR, ARR, new revenue, churned revenue)
    - Revenue by plan breakdown
    - Monthly trends
    - Growth metrics
    """
    # Default to last 30 days if not specified
    if not end_date:
        end_date = datetime.now(timezone.utc)
    if not start_date:
        start_date = end_date - timedelta(days=30)

    service = SubscriptionAnalyticsService(db)

    # Get current metrics
    stats = await service.get_subscription_stats()
    revenue_metrics = await service.get_revenue_metrics()

    # Get historical data
    months = max(1, int((end_date - start_date).days / 30))
    period = "12_months" if months >= 12 else "6_months" if months >= 6 else "3_months"
    revenue_history = await service.get_revenue_history(period)

    # Get plan distribution
    plan_distribution = await service.get_plan_distribution()

    return {
        "data": {
            "report_period": {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "days": (end_date - start_date).days
            },
            "summary": {
                "mrr": stats["data"]["mrr"],
                "arr": stats["data"]["arr"],
                "total_subscriptions": stats["data"]["total_subscriptions"],
                "active_subscriptions": stats["data"]["active_subscriptions"],
                "churn_rate_monthly": stats["data"]["churn_rate_monthly"],
            },
            "revenue_breakdown": revenue_metrics["data"],
            "revenue_history": revenue_history["data"],
            "plan_distribution": plan_distribution["data"],
            "generated_at": datetime.now(timezone.utc).isoformat()
        },
        "message": "Revenue report retrieved successfully"
    }


@router.get("/revenue/export", response_class=Response)
@require_permissions("audit.read", workspace_scoped=False)
@db_transaction_handler("export revenue report", auto_commit=False)
async def export_revenue_report(
    request: Request,
    format: str = Query("csv", regex="^(csv|json)$", description="Export format"),
    start_date: Optional[datetime] = Query(None, description="Start date (ISO format)"),
    end_date: Optional[datetime] = Query(None, description="End date (ISO format)"),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Export revenue report as CSV or JSON (admin only).

    Query Parameters:
    - format: csv or json
    - start_date: Start date (defaults to 30 days ago)
    - end_date: End date (defaults to today)

    Returns:
    - File download (CSV or JSON)
    """
    # Default to last 30 days if not specified
    if not end_date:
        end_date = datetime.now(timezone.utc)
    if not start_date:
        start_date = end_date - timedelta(days=30)

    service = SubscriptionAnalyticsService(db)

    # Get all data
    stats = await service.get_subscription_stats()
    revenue_metrics = await service.get_revenue_metrics()
    plan_distribution = await service.get_plan_distribution()

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    if format == "json":
        import json

        report_data = {
            "report_period": {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "days": (end_date - start_date).days
            },
            "summary": {
                "mrr": stats["data"]["mrr"],
                "arr": stats["data"]["arr"],
                "total_subscriptions": stats["data"]["total_subscriptions"],
                "active_subscriptions": stats["data"]["active_subscriptions"],
            },
            "revenue_by_plan": revenue_metrics["data"]["by_plan"],
            "plan_distribution": plan_distribution["data"],
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "generated_by": current_user.get("email")
        }

        content = json.dumps(report_data, indent=2)
        return Response(
            content=content,
            media_type="application/json",
            headers={
                "Content-Disposition": f"attachment; filename=revenue_report_{timestamp}.json"
            }
        )

    # CSV export
    output = StringIO()
    writer = csv.writer(output)

    # Summary section
    writer.writerow(["Revenue Report Summary"])
    writer.writerow(["Period", f"{start_date.date()} to {end_date.date()}"])
    writer.writerow(["Generated At", datetime.now(timezone.utc).isoformat()])
    writer.writerow(["Generated By", current_user.get("email")])
    writer.writerow([])

    writer.writerow(["Metric", "Value"])
    writer.writerow(["MRR", f"${stats['data']['mrr']:.2f}"])
    writer.writerow(["ARR", f"${stats['data']['arr']:.2f}"])
    writer.writerow(["Total Subscriptions", stats['data']['total_subscriptions']])
    writer.writerow(["Active Subscriptions", stats['data']['active_subscriptions']])
    writer.writerow(["Churn Rate", f"{stats['data']['churn_rate_monthly']:.2f}%"])
    writer.writerow([])

    # Revenue by plan
    writer.writerow(["Revenue by Plan"])
    writer.writerow(["Plan", "Subscriptions", "Monthly Revenue", "Annual Revenue"])
    for plan in revenue_metrics["data"]["by_plan"]:
        writer.writerow([
            plan["plan_display_name"],
            plan["subscription_count"],
            f"${plan['revenue_monthly']:.2f}",
            f"${plan['revenue_yearly']:.2f}"
        ])
    writer.writerow([])

    # Plan distribution
    writer.writerow(["Plan Distribution"])
    writer.writerow(["Plan", "Subscribers", "Percentage"])
    for plan in plan_distribution["data"]:
        writer.writerow([
            plan["plan_display_name"],
            plan["subscription_count"],
            f"{plan['percentage']:.1f}%"
        ])

    csv_content = output.getvalue()
    output.close()

    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=revenue_report_{timestamp}.csv"
        }
    )


@router.get("/revenue/summary", response_model=dict)
@require_permissions("audit.read", workspace_scoped=False)
@db_transaction_handler("get revenue summary", auto_commit=False)
async def get_revenue_summary(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get quick revenue summary for dashboard (admin only).

    Returns:
    - Current month MRR/ARR
    - Previous month comparison
    - Growth rate
    - Quick stats
    """
    service = SubscriptionAnalyticsService(db)

    # Current metrics
    stats = await service.get_subscription_stats()
    revenue_metrics = await service.get_revenue_metrics()

    # Get growth metrics from revenue history
    revenue_history = await service.get_revenue_history("3_months")
    history_data = revenue_history["data"]

    # Calculate month-over-month growth
    current_month_mrr = history_data[-1]["mrr"] if len(history_data) > 0 else 0
    previous_month_mrr = history_data[-2]["mrr"] if len(history_data) > 1 else 0
    mom_growth = 0
    if previous_month_mrr > 0:
        mom_growth = ((current_month_mrr - previous_month_mrr) / previous_month_mrr) * 100

    return {
        "data": {
            "current_month": {
                "mrr": stats["data"]["mrr"],
                "arr": stats["data"]["arr"],
                "active_subscriptions": stats["data"]["active_subscriptions"],
            },
            "previous_month": {
                "mrr": previous_month_mrr,
            },
            "growth": {
                "mom_growth_rate": round(mom_growth, 2),
                "new_revenue_30d": revenue_metrics["data"]["current_month"]["new_revenue"],
            },
            "quick_stats": {
                "churn_rate": stats["data"]["churn_rate_monthly"],
                "trial_conversion": stats["data"]["trial_conversion_rate"],
            }
        },
        "message": "Revenue summary retrieved successfully"
    }
