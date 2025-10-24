"""
Admin Subscription Export API endpoints.

This module provides administrative operations for exporting subscription data,
invoices, and usage reports in CSV format for financial reporting and analysis.

All endpoints require super admin permissions.
"""

import csv
import io
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Request, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, desc

from src.api.database.async_database import get_async_db
from src.api.security.dependencies import get_current_user
from src.api.models.subscription_models.subscriptions import UserSubscription
from src.api.models.subscription_models.plans import SubscriptionPlan
# Note: Invoice model does not exist - invoice export functionality is not implemented
# from src.api.models.subscription_models.invoices import Invoice
from src.api.models.user_models.users import Users
from src.utils.route_decorators import db_transaction_handler, require_permissions
from .shared.auth import require_super_admin


router = APIRouter()


# ============================================================================
# EXPORT ENDPOINTS
# ============================================================================

@router.get("/export/subscriptions", response_class=StreamingResponse)
@require_permissions("subscription.read")
@db_transaction_handler("export subscriptions", auto_commit=False)
async def export_subscriptions_csv(
    request: Request,
    status: Optional[str] = Query(None, description="Filter by status (active, trial, cancelled, etc.)"),
    start_date: Optional[datetime] = Query(None, description="Filter by start date"),
    end_date: Optional[datetime] = Query(None, description="Filter by end date"),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Export subscriptions as CSV (super admin only).

    Query Parameters:
    - status: Filter by subscription status
    - start_date: Filter by subscription start date (from)
    - end_date: Filter by subscription start date (to)

    Returns:
    - CSV file with subscription data
    """
    admin_user_id = current_user.get("identity")
    await require_super_admin(db, admin_user_id)

    # Build filters
    filters = []
    if status:
        from src.api.models.subscription_models.subscriptions import SubscriptionStatus
        try:
            status_enum = SubscriptionStatus(status.upper())
            filters.append(UserSubscription.status == status_enum)
        except ValueError:
            pass  # Invalid status, ignore filter
    if start_date:
        filters.append(UserSubscription.start_date >= start_date)
    if end_date:
        filters.append(UserSubscription.start_date <= end_date)

    # Query subscriptions with user and plan details
    query = (
        select(
            UserSubscription,
            Users.email,
            Users.display_name,
            SubscriptionPlan.name.label("plan_name"),
            SubscriptionPlan.display_name.label("plan_display_name"),
            SubscriptionPlan.price_monthly,
            SubscriptionPlan.price_yearly,
        )
        .join(Users, UserSubscription.user_id == Users.id)
        .join(SubscriptionPlan, UserSubscription.plan_id == SubscriptionPlan.id)
        .order_by(desc(UserSubscription.start_date))
    )

    if filters:
        query = query.where(and_(*filters))

    result = await db.execute(query)
    subscriptions = result.all()

    # Create CSV in memory
    output = io.StringIO()
    writer = csv.writer(output)

    # Write header
    writer.writerow([
        "Subscription ID",
        "User Email",
        "User Name",
        "Plan Name",
        "Plan Display Name",
        "Status",
        "Billing Period",
        "Price (Monthly)",
        "Price (Yearly)",
        "Start Date",
        "End Date",
        "Trial End Date",
        "Cancelled At",
        "LemonSqueezy ID",
        "Created At",
        "Updated At",
    ])

    # Write data rows
    for sub, user_email, user_name, plan_name, plan_display, price_monthly, price_yearly in subscriptions:
        writer.writerow([
            str(sub.id),
            user_email,
            user_name or "",
            plan_name,
            plan_display,
            sub.status.value if sub.status else "",
            sub.billing_period.value if sub.billing_period else "",
            float(price_monthly) if price_monthly else 0.0,
            float(price_yearly) if price_yearly else 0.0,
            sub.start_date.isoformat() if sub.start_date else "",
            sub.end_date.isoformat() if sub.end_date else "",
            sub.trial_end_date.isoformat() if sub.trial_end_date else "",
            sub.cancelled_at.isoformat() if sub.cancelled_at else "",
            sub.lemonsqueezy_subscription_id or "",
            sub.created_at.isoformat() if sub.created_at else "",
            sub.updated_at.isoformat() if sub.updated_at else "",
        ])

    # Prepare response
    output.seek(0)
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = f"subscriptions_export_{timestamp}.csv"

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename={filename}",
            "X-Total-Records": str(len(subscriptions)),
        }
    )


@router.get("/export/invoices", response_class=StreamingResponse)
@require_permissions("subscription.read")
@db_transaction_handler("export invoices", auto_commit=False)
async def export_invoices_csv(
    request: Request,
    status: Optional[str] = Query(None, description="Filter by status (paid, pending, refunded)"),
    start_date: Optional[datetime] = Query(None, description="Filter by invoice date (from)"),
    end_date: Optional[datetime] = Query(None, description="Filter by invoice date (to)"),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Export invoices as CSV (super admin only).

    Query Parameters:
    - status: Filter by invoice status
    - start_date: Filter by invoice date (from)
    - end_date: Filter by invoice date (to)

    Returns:
    - CSV file with invoice data

    Raises:
        NotImplementedError: Invoice model does not exist yet
    """
    # TODO: Implement invoice export when Invoice model is created
    # The Invoice database model does not exist in the codebase.
    # This functionality requires creating the Invoice model and migration first.
    raise NotImplementedError(
        "Invoice export is not available. The Invoice database model has not been implemented yet."
    )


@router.get("/export/revenue-summary", response_class=StreamingResponse)
@require_permissions("subscription.read")
@db_transaction_handler("export revenue summary", auto_commit=False)
async def export_revenue_summary_csv(
    request: Request,
    start_date: Optional[datetime] = Query(None, description="Filter by date (from)"),
    end_date: Optional[datetime] = Query(None, description="Filter by date (to)"),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Export revenue summary as CSV (super admin only).

    Groups revenue by plan and billing period for financial reporting.

    Query Parameters:
    - start_date: Filter by subscription start date (from)
    - end_date: Filter by subscription start date (to)

    Returns:
    - CSV file with revenue summary data
    """
    admin_user_id = current_user.get("identity")
    await require_super_admin(db, admin_user_id)

    # Import here to avoid circular imports
    from src.api.models.subscription_models.subscriptions import SubscriptionStatus, BillingPeriod
    from sqlalchemy import func, case

    # Build filters
    filters = [
        UserSubscription.status.in_([SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL])
    ]
    if start_date:
        filters.append(UserSubscription.start_date >= start_date)
    if end_date:
        filters.append(UserSubscription.start_date <= end_date)

    # Query revenue grouped by plan and billing period
    query = (
        select(
            SubscriptionPlan.name.label("plan_name"),
            SubscriptionPlan.display_name.label("plan_display_name"),
            UserSubscription.billing_period,
            func.count(UserSubscription.id).label("subscription_count"),
            func.sum(
                case(
                    (UserSubscription.billing_period == BillingPeriod.MONTHLY, SubscriptionPlan.price_monthly),
                    (UserSubscription.billing_period == BillingPeriod.YEARLY, SubscriptionPlan.price_yearly),
                    else_=0,
                )
            ).label("total_revenue"),
            func.sum(
                case(
                    (UserSubscription.billing_period == BillingPeriod.MONTHLY, SubscriptionPlan.price_monthly),
                    (UserSubscription.billing_period == BillingPeriod.YEARLY, SubscriptionPlan.price_yearly / 12),
                    else_=0,
                )
            ).label("mrr_contribution"),
        )
        .join(UserSubscription, SubscriptionPlan.id == UserSubscription.plan_id)
        .where(and_(*filters))
        .group_by(
            SubscriptionPlan.name,
            SubscriptionPlan.display_name,
            UserSubscription.billing_period,
        )
        .order_by(SubscriptionPlan.name, UserSubscription.billing_period)
    )

    result = await db.execute(query)
    revenue_data = result.all()

    # Create CSV in memory
    output = io.StringIO()
    writer = csv.writer(output)

    # Write header
    writer.writerow([
        "Plan Name",
        "Plan Display Name",
        "Billing Period",
        "Active Subscriptions",
        "Total Revenue",
        "MRR Contribution",
        "ARR Contribution",
    ])

    # Write data rows
    total_subscriptions = 0
    total_revenue = 0.0
    total_mrr = 0.0

    for plan_name, plan_display, billing_period, count, revenue, mrr in revenue_data:
        total_subscriptions += count
        total_revenue += float(revenue or 0)
        total_mrr += float(mrr or 0)

        writer.writerow([
            plan_name,
            plan_display,
            billing_period.value if billing_period else "",
            count,
            f"{float(revenue or 0):.2f}",
            f"{float(mrr or 0):.2f}",
            f"{float(mrr or 0) * 12:.2f}",
        ])

    # Write summary row
    writer.writerow([])
    writer.writerow([
        "TOTAL",
        "",
        "",
        total_subscriptions,
        f"{total_revenue:.2f}",
        f"{total_mrr:.2f}",
        f"{total_mrr * 12:.2f}",
    ])

    # Prepare response
    output.seek(0)
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = f"revenue_summary_{timestamp}.csv"

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename={filename}",
            "X-Total-Records": str(len(revenue_data)),
            "X-Total-Subscriptions": str(total_subscriptions),
            "X-Total-MRR": f"{total_mrr:.2f}",
        }
    )


@router.get("/export/trial-conversions", response_class=StreamingResponse)
@require_permissions("subscription.read")
@db_transaction_handler("export trial conversions", auto_commit=False)
async def export_trial_conversions_csv(
    request: Request,
    start_date: Optional[datetime] = Query(None, description="Filter by trial start date (from)"),
    end_date: Optional[datetime] = Query(None, description="Filter by trial start date (to)"),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Export trial conversion data as CSV (super admin only).

    Shows all subscriptions that had trials, their conversion status,
    and timing metrics.

    Query Parameters:
    - start_date: Filter by trial start date (from)
    - end_date: Filter by trial start date (to)

    Returns:
    - CSV file with trial conversion data
    """
    admin_user_id = current_user.get("identity")
    await require_super_admin(db, admin_user_id)

    from src.api.models.subscription_models.subscriptions import SubscriptionStatus

    # Build filters - subscriptions that have/had trials
    filters = [UserSubscription.trial_end_date.isnot(None)]
    if start_date:
        filters.append(UserSubscription.start_date >= start_date)
    if end_date:
        filters.append(UserSubscription.start_date <= end_date)

    # Query trial subscriptions
    query = (
        select(
            UserSubscription,
            Users.email,
            Users.display_name,
            SubscriptionPlan.name.label("plan_name"),
            SubscriptionPlan.display_name.label("plan_display_name"),
        )
        .join(Users, UserSubscription.user_id == Users.id)
        .join(SubscriptionPlan, UserSubscription.plan_id == SubscriptionPlan.id)
        .where(and_(*filters))
        .order_by(desc(UserSubscription.start_date))
    )

    result = await db.execute(query)
    trials = result.all()

    # Create CSV in memory
    output = io.StringIO()
    writer = csv.writer(output)

    # Write header
    writer.writerow([
        "Subscription ID",
        "User Email",
        "User Name",
        "Plan Name",
        "Current Status",
        "Trial Start Date",
        "Trial End Date",
        "Trial Length (Days)",
        "Converted to Paid",
        "Conversion Date",
        "Time to Convert (Days)",
        "Created At",
    ])

    # Write data rows
    for sub, user_email, user_name, plan_name, plan_display in trials:
        # Determine if converted
        converted = sub.status == SubscriptionStatus.ACTIVE
        conversion_date = sub.updated_at if converted else None

        # Calculate trial length
        trial_length = ""
        if sub.start_date and sub.trial_end_date:
            trial_length = (sub.trial_end_date - sub.start_date).days

        # Calculate time to convert
        time_to_convert = ""
        if converted and sub.start_date and sub.updated_at:
            time_to_convert = (sub.updated_at - sub.start_date).days

        writer.writerow([
            str(sub.id),
            user_email,
            user_name or "",
            plan_name,
            sub.status.value if sub.status else "",
            sub.start_date.isoformat() if sub.start_date else "",
            sub.trial_end_date.isoformat() if sub.trial_end_date else "",
            trial_length,
            "Yes" if converted else "No",
            conversion_date.isoformat() if conversion_date else "",
            time_to_convert,
            sub.created_at.isoformat() if sub.created_at else "",
        ])

    # Prepare response
    output.seek(0)
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = f"trial_conversions_{timestamp}.csv"

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename={filename}",
            "X-Total-Records": str(len(trials)),
        }
    )
