"""
Admin Webhook Monitoring API endpoints.

This module provides administrative operations for monitoring webhook events
from LemonSqueezy including viewing recent events, failed events, and retry operations.

All endpoints require super admin permissions.
"""

from datetime import datetime, timedelta, timezone
from typing import Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request
from sqlalchemy import and_, case, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.database.async_database import get_async_db
from src.api.models.subscription_models.webhooks import WebhookEvent
from src.api.schema.response.admin_subscription_webhook_responses import (
    FailedWebhookListResponse,
    WebhookEventListResponse,
    WebhookEventRow,
    WebhookRetryResponse,
    WebhookStatisticsResponse,
)
from src.api.schema.response_schemas import SuccessResponse
from src.api.security.dependencies import get_current_user
from src.services.webhook_monitoring_service import WebhookMonitoringService
from src.utils.response_utils import success
from src.utils.route_decorators import db_transaction_handler, require_permissions

from .shared.auth import require_super_admin

router = APIRouter()


# ============================================================================
# WEBHOOK MONITORING ENDPOINTS
# ============================================================================


@router.get("/webhooks/events", response_model=SuccessResponse[WebhookEventListResponse])
@require_permissions("billing.read", workspace_scoped=False)
@db_transaction_handler("get webhook events", auto_commit=False)
async def get_webhook_events(
    request: Request,
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(50, ge=1, le=200, description="Items per page"),
    event_name: Optional[str] = Query(None, description="Filter by event name"),
    processed: Optional[bool] = Query(
        None, description="Filter by processed status (deprecated - use `status`)"
    ),
    status: Optional[Literal["all", "processed", "pending", "failed"]] = Query(
        None, description="Filter rows by lifecycle status"
    ),
    start_date: Optional[datetime] = Query(None, description="Start date filter"),
    end_date: Optional[datetime] = Query(None, description="End date filter"),
    include_payload: bool = Query(False, description="Include redacted payload body"),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
):
    """
    List recent webhook events (requires security.read permission).

    Query Parameters:
    - page: Page number (default 1)
    - per_page: Items per page (default 50, max 200)
    - event_name: Filter by event name (e.g., "subscription_created")
    - status: one of `processed` / `pending` / `failed` / `all`. Applied to the
      returned rows and the `pagination.total`. `failed` = not processed and has
      an error; `pending` = not processed and no error.
    - processed: legacy boolean filter (kept for backward compatibility)
    - start_date / end_date: creation-time window (ISO format)

    Returns:
    - `events`: the page of rows matching `status` (+ event_name + date window)
    - `pagination`: page metadata for that filtered set
    - `summary`: counts for the whole window (event_name + date only, NOT
      narrowed by `status`) so the UI tab counts stay stable and satisfy
      `processed + pending + failed == total`
    """
    admin_user_id = current_user.get("identity")
    await require_super_admin(db, admin_user_id)

    # Window filters — shared by the row list AND the summary.
    window_filters = []
    if event_name:
        clean_event = event_name.strip()
        if clean_event:
            window_filters.append(WebhookEvent.event_name.ilike(f"%{clean_event}%"))
    if start_date:
        window_filters.append(WebhookEvent.created_at >= start_date)
    if end_date:
        window_filters.append(WebhookEvent.created_at <= end_date)

    _PROCESSED = WebhookEvent.processed
    _HAS_ERROR = WebhookEvent.error_message.isnot(None)
    _NO_ERROR = WebhookEvent.error_message.is_(None)

    # Status filter — applied ONLY to the row list + its pagination total.
    row_filters = list(window_filters)
    effective_status = status
    if effective_status is None and processed is not None:
        effective_status = "processed" if processed else "pending"

    if effective_status == "processed":
        row_filters.append(_PROCESSED.is_(True))
    elif effective_status == "failed":
        row_filters.append(and_(_PROCESSED.is_(False), _HAS_ERROR))
    elif effective_status == "pending":
        row_filters.append(and_(_PROCESSED.is_(False), _NO_ERROR))

    # Count rows for the active status filter
    count_query = select(func.count(WebhookEvent.id))
    if row_filters:
        count_query = count_query.where(and_(*row_filters))
    total_result = await db.execute(count_query)
    total_events = total_result.scalar() or 0

    # Get paginated events
    offset = (page - 1) * per_page
    query = select(WebhookEvent)
    if row_filters:
        query = query.where(and_(*row_filters))
    query = query.order_by(desc(WebhookEvent.created_at)).offset(offset).limit(per_page)

    result = await db.execute(query)
    events = result.scalars().all()

    # Summary — whole window, independent of the status filter, internally
    # consistent (processed + pending + failed == total).
    stats_query = select(
        func.count(WebhookEvent.id).label("total"),
        func.sum(case((_PROCESSED, 1), else_=0)).label("processed_count"),
        func.sum(case((and_(~_PROCESSED, _NO_ERROR), 1), else_=0)).label("pending_count"),
        func.sum(case((and_(~_PROCESSED, _HAS_ERROR), 1), else_=0)).label("failed_count"),
    )
    if window_filters:
        stats_query = stats_query.where(and_(*window_filters))

    stats_result = await db.execute(stats_query)
    stats_row = stats_result.first()

    summary = {
        "total": stats_row.total or 0,
        "processed": stats_row.processed_count or 0,
        "pending": stats_row.pending_count or 0,
        "failed": stats_row.failed_count or 0,
    }

    # Format events
    events_data = []
    for event in events:
        event_dict = event.to_dict(include_payload=include_payload)
        # Add status indicator
        if event.processed:
            event_dict["status"] = "processed"
        elif event.error_message:
            event_dict["status"] = "failed"
        else:
            event_dict["status"] = "pending"
        events_data.append(event_dict)

    result_data = {
        "events": events_data,
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total": total_events,
            "total_pages": (total_events + per_page - 1) // per_page,
        },
        "summary": summary,
    }
    return success(
        data=result_data, request=request, message="Webhook events retrieved successfully"
    )


@router.get("/webhooks/failed", response_model=SuccessResponse[FailedWebhookListResponse])
@require_permissions("billing.read", workspace_scoped=False)
@db_transaction_handler("get failed webhook events", auto_commit=False)
async def get_failed_webhook_events(
    request: Request,
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(50, ge=1, le=200, description="Items per page"),
    hours: int = Query(
        24, ge=1, le=720, description="Look back hours (default 24, max 720/30 days)"
    ),
    include_payload: bool = Query(False, description="Include redacted payload body"),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
):
    """
    List failed webhook events (requires security.read permission).

    Failed events are webhooks that have not been processed successfully
    and have an error message recorded.

    Query Parameters:
    - page: Page number (default 1)
    - per_page: Items per page (default 50, max 200)
    - hours: Look back period in hours (default 24, max 720/30 days)

    Returns:
    - List of failed webhook events with error details
    - Pagination metadata
    - Failure statistics
    """
    admin_user_id = current_user.get("identity")
    await require_super_admin(db, admin_user_id)

    # Calculate time filter
    since_date = datetime.now(timezone.utc) - timedelta(hours=hours)

    # Build filters for failed events
    filters = [
        WebhookEvent.processed.is_(False),
        WebhookEvent.error_message.isnot(None),
        WebhookEvent.created_at >= since_date,
    ]

    # Count total failed events
    count_query = select(func.count(WebhookEvent.id)).where(and_(*filters))
    total_result = await db.execute(count_query)
    total_failed = total_result.scalar() or 0

    # Get paginated failed events
    offset = (page - 1) * per_page
    query = (
        select(WebhookEvent)
        .where(and_(*filters))
        .order_by(desc(WebhookEvent.created_at))
        .offset(offset)
        .limit(per_page)
    )

    result = await db.execute(query)
    failed_events = result.scalars().all()

    # Get failure statistics by event type
    stats_query = (
        select(
            WebhookEvent.event_name,
            func.count(WebhookEvent.id).label("count"),
            func.max(WebhookEvent.retry_count).label("max_retries"),
        )
        .where(and_(*filters))
        .group_by(WebhookEvent.event_name)
        .order_by(desc(func.count(WebhookEvent.id)))
    )

    stats_result = await db.execute(stats_query)
    failure_stats = []
    for row in stats_result.all():
        failure_stats.append(
            {
                "event_name": row.event_name,
                "failure_count": row.count,
                "max_retries": row.max_retries,
            }
        )

    # Format failed events
    events_data = []
    for event in failed_events:
        event_dict = event.to_dict(include_payload=include_payload)
        event_dict["status"] = "failed"
        # Include time since failure
        if event.created_at:
            minutes_ago = int((datetime.now(timezone.utc) - event.created_at).total_seconds() / 60)
            event_dict["minutes_since_failure"] = minutes_ago
        events_data.append(event_dict)

    result_data = {
        "failed_events": events_data,
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total": total_failed,
            "total_pages": (total_failed + per_page - 1) // per_page,
        },
        "statistics": {
            "total_failed": total_failed,
            "time_period_hours": hours,
            "failures_by_type": failure_stats,
        },
    }
    return success(
        data=result_data,
        request=request,
        message=f"Failed webhook events from last {hours} hours retrieved successfully",
    )


@router.get("/webhooks/detail/{webhook_id}", response_model=SuccessResponse[WebhookEventRow])
@require_permissions("billing.read", workspace_scoped=False)
@db_transaction_handler("get webhook event detail", auto_commit=False)
async def get_webhook_event_detail(
    request: Request,
    webhook_id: UUID = Path(..., description="Webhook event database id (webhook_events.id)"),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Get a single webhook event including its (redacted) payload.

    Path Parameters:
    - webhook_id: The database id of the webhook event (``webhook_events.id``)

    Returns the full event record with the payload body redacted for PII so the
    admin payload viewer can inspect the raw event structure.
    """
    admin_user_id = current_user.get("identity")
    await require_super_admin(db, admin_user_id)

    query = select(WebhookEvent).where(WebhookEvent.id == webhook_id)
    result = await db.execute(query)
    webhook_event = result.scalar_one_or_none()

    if not webhook_event:
        raise HTTPException(status_code=404, detail="Webhook event not found")

    service = WebhookMonitoringService(db)
    event_dict = webhook_event.to_dict(include_payload=True)
    if webhook_event.payload:
        event_dict["payload"] = service._redact_payload(webhook_event.payload)
    if webhook_event.processed:
        event_dict["status"] = "processed"
    elif webhook_event.error_message:
        event_dict["status"] = "failed"
    else:
        event_dict["status"] = "pending"

    return success(
        data=event_dict,
        request=request,
        message="Webhook event retrieved successfully",
    )


@router.post("/webhooks/{webhook_id}/retry", response_model=SuccessResponse[WebhookRetryResponse])
@require_permissions("billing.manage", workspace_scoped=False)
@db_transaction_handler("retry failed webhook", auto_commit=False)
async def retry_failed_webhook(
    request: Request,
    webhook_id: UUID = Path(..., description="Webhook event database id (webhook_events.id)"),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Retry a failed webhook event (requires security.read permission).

    Identifier contract:
    - The path parameter is the database id of the webhook event
      (``webhook_events.id``, a UUID) - the same ``id`` returned by the list
      endpoints. The external LemonSqueezy ``event_id`` is looked up from the
      stored row when needed for processing; callers never pass it directly.

    The stored payload is re-routed through the full webhook handler registry in
    a dedicated transaction. The event row and its resulting status are persisted
    independently, so a failed retry is still recorded.

    Returns HTTP 200 with ``{success: true, data: <event>}`` when reprocessing
    succeeds, and HTTP 400 with an error detail when it fails (or the event is
    not found / already processed).
    """
    admin_user_id = current_user.get("identity")
    await require_super_admin(db, admin_user_id)

    service = WebhookMonitoringService(db)
    result = await service.retry_webhook(webhook_id)

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("message", "Retry failed"))

    result_data = {
        "success": True,
        "event": result.get("event"),
        "message": result.get("message"),
    }
    return success(
        data=result_data,
        request=request,
        message=result.get("message", "Webhook reprocessed successfully"),
    )


@router.get("/webhooks/stats", response_model=SuccessResponse[WebhookStatisticsResponse])
@require_permissions("billing.read", workspace_scoped=False)
@db_transaction_handler("get webhook statistics", auto_commit=False)
async def get_webhook_statistics(
    request: Request,
    days: Optional[int] = Query(None, ge=1, description="Look back days (None for all time)"),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Get webhook processing statistics (requires security.read permission).

    Query Parameters:
    - days: Look back period in days (default 7, None for all time)

    Returns:
    - Processing statistics by event type
    - Success/failure rates
    - Processing time metrics
    """
    admin_user_id = current_user.get("identity")
    await require_super_admin(db, admin_user_id)

    # Calculate time filter
    since_date = None
    if days is not None:
        since_date = datetime.now(timezone.utc) - timedelta(days=days)

    # Get overall statistics
    overall_query = select(
        func.count(WebhookEvent.id).label("total"),
        func.sum(case((WebhookEvent.processed, 1), else_=0)).label("processed"),
        func.sum(
            case(
                (and_(~WebhookEvent.processed, WebhookEvent.error_message.isnot(None)), 1),
                else_=0,
            )
        ).label("failed"),
        func.avg(WebhookEvent.retry_count).label("avg_retries"),
    )
    if since_date:
        overall_query = overall_query.where(WebhookEvent.created_at >= since_date)

    overall_result = await db.execute(overall_query)
    overall_stats = overall_result.first()

    total_events = overall_stats.total or 0
    processed_events = overall_stats.processed or 0
    failed_events = overall_stats.failed or 0
    avg_retries = float(overall_stats.avg_retries or 0)

    success_rate = (processed_events / total_events * 100) if total_events > 0 else 0
    failure_rate = (failed_events / total_events * 100) if total_events > 0 else 0

    # Get statistics by event type
    by_type_query = (
        select(
            WebhookEvent.event_name,
            func.count(WebhookEvent.id).label("total"),
            func.sum(case((WebhookEvent.processed, 1), else_=0)).label("processed"),
            func.sum(
                case(
                    (and_(~WebhookEvent.processed, WebhookEvent.error_message.isnot(None)), 1),
                    else_=0,
                )
            ).label("failed"),
        )
        .group_by(WebhookEvent.event_name)
        .order_by(desc(func.count(WebhookEvent.id)))
    )
    if since_date:
        by_type_query = by_type_query.where(WebhookEvent.created_at >= since_date)

    by_type_result = await db.execute(by_type_query)
    by_type_stats = []
    for row in by_type_result.all():
        total = row.total or 0
        processed = row.processed or 0
        failed = row.failed or 0
        success_rate_type = (processed / total * 100) if total > 0 else 0

        by_type_stats.append(
            {
                "event_name": row.event_name,
                "total": total,
                "processed": processed,
                "failed": failed,
                "success_rate": round(success_rate_type, 2),
            }
        )

    result_data = {
        "period": {
            "days": days,
            "since": since_date.isoformat() if since_date else None,
            "all_time": since_date is None,
        },
        "overall": {
            "total_events": total_events,
            "processed": processed_events,
            "failed": failed_events,
            "pending": total_events - processed_events - failed_events,
            "success_rate": round(success_rate, 2),
            "failure_rate": round(failure_rate, 2),
            "average_retries": round(avg_retries, 2),
        },
        "by_event_type": by_type_stats,
    }
    period_label = f"last {days} days" if days else "all time"
    return success(
        data=result_data,
        request=request,
        message=f"Webhook statistics for {period_label} retrieved successfully",
    )
