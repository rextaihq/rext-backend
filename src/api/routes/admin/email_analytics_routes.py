"""
Email Analytics Routes

Admin-only routes for email analytics and performance monitoring.
Supports workspace-scoped filtering for multi-tenancy.
"""
from typing import Literal, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, Request, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.database.async_database import get_async_db
from src.api.security.dependencies import get_current_user
from src.services.email_analytics_service import EmailAnalyticsService
from src.utils.response_utils import success
from src.utils.route_decorators import db_transaction_handler, require_permissions
from src.api.cache.decorators import cached


router = APIRouter(
    prefix="/admin/email-analytics",
    tags=["admin", "email-analytics"]
)


@router.get("/overview")
@db_transaction_handler("get email analytics overview", auto_commit=False)
@require_permissions("audit.admin", workspace_scoped=False)
@cached(key_prefix="admin:email:overview", ttl=300)
async def get_email_analytics_overview(
    request: Request,
    date_range: str = Query("30d", description="Date range (e.g., 7d, 30d, 90d)"),
    workspace_id: Optional[str] = Query(None, description="Optional workspace ID for filtering (multi-tenancy)"),
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user)
):
    """
    Get email analytics overview

    **Permissions Required:** audit.read (admin monitoring)

    **Query Parameters:**
    - `date_range`: Date range string (e.g., "7d", "30d", "90d")
    - `workspace_id`: Optional workspace ID to filter by workspace (multi-tenancy support)

    **Response:**
    ```json
    {
        "total_sent": 5000,
        "total_delivered": 4850,
        "total_opened": 1200,
        "total_clicked": 300,
        "total_bounced": 50,
        "total_complained": 5,
        "delivery_rate": 97.0,
        "open_rate": 24.7,
        "click_rate": 6.2,
        "bounce_rate": 1.0,
        "complaint_rate": 0.1
    }
    ```
    """
    service = EmailAnalyticsService(db)

    # Convert workspace_id string to UUID if provided
    workspace_uuid = UUID(workspace_id) if workspace_id else None

    stats = await service.get_overview_stats(date_range, workspace_uuid)

    message = f"Email analytics overview for {date_range}"
    if workspace_id:
        message += f" (workspace: {workspace_id[:8]}...)"

    return success(
        data=stats,
        request=request,
        message=message
    )


@router.get("/by-template")
@db_transaction_handler("get email analytics by template", auto_commit=False)
@require_permissions("audit.admin", workspace_scoped=False)
@cached(key_prefix="admin:email:templates", ttl=300)
async def get_email_analytics_by_template(
    request: Request,
    date_range: str = Query("30d", description="Date range (e.g., 7d, 30d, 90d)"),
    workspace_id: Optional[str] = Query(None, description="Optional workspace ID for filtering (multi-tenancy)"),
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user)
):
    """
    Get email performance by template type

    **Permissions Required:** audit.read (admin monitoring)

    **Query Parameters:**
    - `date_range`: Date range string
    - `workspace_id`: Optional workspace ID to filter by workspace (multi-tenancy support)

    **Response:**
    ```json
    [
        {
            "template_type": "content_generation_completed",
            "sent": 500,
            "delivered": 490,
            "opened": 250,
            "clicked": 80,
            "open_rate": 51.0,
            "click_rate": 16.3
        }
    ]
    ```
    """
    service = EmailAnalyticsService(db)

    # Convert workspace_id string to UUID if provided
    workspace_uuid = UUID(workspace_id) if workspace_id else None

    template_stats = await service.get_analytics_by_template(date_range, workspace_uuid)

    message = f"Email analytics by template for {date_range}"
    if workspace_id:
        message += f" (workspace: {workspace_id[:8]}...)"

    return success(
        data={"templates": template_stats, "total_count": len(template_stats)},
        request=request,
        message=message
    )


@router.get("/timeline")
@db_transaction_handler("get email timeline", auto_commit=False)
@require_permissions("audit.admin", workspace_scoped=False)
@cached(key_prefix="admin:email:timeline", ttl=300)
async def get_email_timeline(
    request: Request,
    period: Literal["daily", "weekly", "monthly"] = Query(
        "daily",
        description="Aggregation period (allowed: daily, weekly, monthly)"
    ),
    date_range: str = Query("30d", description="Date range (e.g., 7d, 30d, 90d)"),
    workspace_id: Optional[str] = Query(None, description="Optional workspace ID for filtering (multi-tenancy)"),
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user)
):
    """
    Get email volume over time

    **Permissions Required:** audit.read (admin monitoring)

    **Query Parameters:**
    - `period`: Aggregation period ("daily", "weekly", "monthly")
    - `date_range`: Date range string
    - `workspace_id`: Optional workspace ID to filter by workspace (multi-tenancy support)

    **Response:**
    ```json
    [
        {
            "date": "2025-10-01T00:00:00",
            "sent": 150,
            "opened": 40,
            "clicked": 10
        }
    ]
    ```
    """
    service = EmailAnalyticsService(db)

    # Convert workspace_id string to UUID if provided
    workspace_uuid = UUID(workspace_id) if workspace_id else None

    timeline = await service.get_timeline(period, date_range, workspace_uuid)

    message = f"Email timeline ({period}) for {date_range}"
    if workspace_id:
        message += f" (workspace: {workspace_id[:8]}...)"

    return success(
        data={"timeline": timeline, "total_count": len(timeline)},
        request=request,
        message=message
    )


@router.get("/failures")
@db_transaction_handler("get email failures", auto_commit=False)
@require_permissions("audit.admin", workspace_scoped=False)
@cached(key_prefix="admin:email:failures", ttl=300)
async def get_email_failures(
    request: Request,
    limit: int = Query(100, ge=1, le=500, description="Maximum number of failures"),
    workspace_id: Optional[str] = Query(None, description="Optional workspace ID for filtering (multi-tenancy)"),
    db: AsyncSession = Depends(get_async_db),
    user: dict = Depends(get_current_user)
):
    """
    Get recent email failures

    **Permissions Required:** audit.read (admin monitoring)

    **Query Parameters:**
    - `limit`: Maximum number of failures to return (1-500)
    - `workspace_id`: Optional workspace ID to filter by workspace (multi-tenancy support)

    **Response:**
    ```json
    [
        {
            "id": "uuid",
            "to": "user@example.com",
            "template_type": "payment_succeeded",
            "status": "bounced",
            "error_message": "550 5.1.1 User unknown",
            "sent_at": "2025-10-12T10:00:00Z"
        }
    ]
    ```
    """
    service = EmailAnalyticsService(db)

    # Convert workspace_id string to UUID if provided
    workspace_uuid = UUID(workspace_id) if workspace_id else None

    failures = await service.get_recent_failures(limit, workspace_uuid)

    message = f"Retrieved {len(failures)} recent email failures"
    if workspace_id:
        message += f" (workspace: {workspace_id[:8]}...)"

    return success(
        data={"failures": failures, "total_count": len(failures)},
        request=request,
        message=message
    )
