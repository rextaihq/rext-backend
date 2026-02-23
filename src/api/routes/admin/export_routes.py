"""
Admin Export API endpoints.

This module provides CSV export functionality for:
- Subscriptions
- Invoices
- Usage data
- Revenue summaries

All endpoints require super admin permissions.
"""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Request, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.database.async_database import get_async_db
from src.api.security.dependencies import get_current_user
from src.services.subscription_export_service import SubscriptionExportService
from src.utils.route_decorators import db_transaction_handler, require_permissions
from src.api.routes.subscriptions.admin.shared.auth import require_super_admin
from src.api.routes.subscriptions.admin.shared.auth import require_super_admin_user


router = APIRouter()


# ============================================================================
# EXPORT ENDPOINTS
# ============================================================================

@router.get("/export/subscriptions")
@require_permissions("subscription.read", workspace_scoped=False)
@db_transaction_handler("export subscriptions", auto_commit=False)
async def export_subscriptions(
    request: Request,
    status: str = Query(None, description="Filter by subscription status"),
    plan_id: str = Query(None, description="Filter by plan ID"),
    start_date: datetime = Query(None, description="Filter by start date (ISO 8601)"),
    end_date: datetime = Query(None, description="Filter by end date (ISO 8601)"),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(require_super_admin_user),
):
    """
    Export subscriptions to CSV (super admin only).

    Query Parameters:
    - status: Filter by subscription status (optional)
    - plan_id: Filter by plan ID (optional)
    - start_date: Filter subscriptions created after this date (optional)
    - end_date: Filter subscriptions created before this date (optional)

    Returns:
    - CSV file download with subscriptions data
    """
    admin_user_id = current_user.get("identity")
    await require_super_admin(db, admin_user_id)

    service = SubscriptionExportService(db)
    csv_content = await service.export_subscriptions_csv(
        status=status,
        plan_id=plan_id,
        start_date=start_date,
        end_date=end_date
    )

    # Generate filename with timestamp
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"subscriptions_export_{timestamp}.csv"

    return StreamingResponse(
        iter([csv_content]),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f"attachment; filename={filename}"
        }
    )


@router.get("/export/invoices")
@require_permissions("subscription.read", workspace_scoped=False)
@db_transaction_handler("export invoices", auto_commit=False)
async def export_invoices(
    request: Request,
    status: str = Query(None, description="Filter by invoice status"),
    start_date: datetime = Query(None, description="Filter by invoice date (ISO 8601)"),
    end_date: datetime = Query(None, description="Filter by invoice date (ISO 8601)"),
    min_amount: float = Query(None, description="Filter by minimum amount"),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(require_super_admin_user)
):
    """
    Export invoices to CSV (super admin only).

    Query Parameters:
    - status: Filter by invoice status (optional)
    - start_date: Filter invoices created after this date (optional)
    - end_date: Filter invoices created before this date (optional)
    - min_amount: Filter by minimum invoice amount (optional)

    Returns:
    - CSV file download with invoices data
    """
    admin_user_id = current_user.get("identity")
    await require_super_admin(db, admin_user_id)

    service = SubscriptionExportService(db)
    try:
        csv_content = await service.export_invoices_csv(
            status=status,
            start_date=start_date,
            end_date=end_date,
            min_amount=min_amount
        )
    except NotImplementedError:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=501,
            detail="Invoice export is not available yet"
        )

    # Create streaming response
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"invoices_export_{timestamp}.csv"

    return StreamingResponse(
        iter([csv_content]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename={filename}"
        }
    )


@router.get("/export/usage")
@require_permissions("subscription.read", workspace_scoped=False)
@db_transaction_handler("export usage data", auto_commit=False)
async def export_usage_data(
    request: Request,
    user_id: str = Query(None, description="Filter by user ID"),
    start_date: datetime = Query(None, description="Filter by date (ISO 8601)"),
    end_date: datetime = Query(None, description="Filter by date (ISO 8601)"),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(require_super_admin_user)
):
    """
    Export usage data to CSV (super admin only).

    Query Parameters:
    - user_id: Filter by specific user (optional)
    - start_date: Filter subscriptions started after this date (optional)
    - end_date: Filter subscriptions started before this date (optional)

    Returns:
    - CSV file download with usage data including plan limits and activity
    """
    admin_user_id = current_user.get("identity")
    await require_super_admin(db, admin_user_id)

    service = SubscriptionExportService(db)
    csv_content = await service.export_usage_data_csv(
        user_id=user_id,
        start_date=start_date,
        end_date=end_date
    )

    # Create streaming response
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"usage_export_{timestamp}.csv"

    return StreamingResponse(
        iter([csv_content]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename={filename}"
        }
    )


@router.get("/export/revenue-summary")
@require_permissions("subscription.read", workspace_scoped=False)
@db_transaction_handler("export revenue summary", auto_commit=False)
async def export_revenue_summary(
    request: Request,
    months: int = Query(12, ge=1, le=36, description="Number of months to include"),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(require_super_admin_user)
):
    """
    Export revenue summary by month to CSV (super admin only).

    Query Parameters:
    - months: Number of months to include in the report (default 12, max 36)

    Returns:
    - CSV file download with monthly revenue summary including:
      - New subscriptions
      - Cancellations
      - Revenue changes
      - MRR trends
    """
    admin_user_id = current_user.get("identity")
    await require_super_admin(db, admin_user_id)

    service = SubscriptionExportService(db)
    csv_content = await service.export_revenue_summary_csv(months=months)

    # Create streaming response
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"revenue_summary_{months}m_{timestamp}.csv"

    return StreamingResponse(
        iter([csv_content]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename={filename}"
        }
    )
