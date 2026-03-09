"""
Admin Webhook Monitoring API endpoints.

This module provides administrative operations for monitoring webhook events
from LemonSqueezy including viewing recent events, failed events, and retry operations.

All endpoints require super admin permissions.
"""

from typing import Optional
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, Request, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, desc, func, Integer

from src.api.database.async_database import get_async_db
from src.api.security.dependencies import get_current_user
from src.api.schema.response_schemas import SuccessResponse
from src.api.schema.__response__.admin_subscription_webhook_responses import (
    WebhookEventListResponse,
    FailedWebhookListResponse,
    WebhookRetryResponse,
    WebhookStatisticsResponse,
)
from src.api.models.subscription_models.webhooks import WebhookEvent
from src.utils.route_decorators import db_transaction_handler, require_permissions
from src.utils.response_utils import success
from .shared.auth import require_super_admin


router = APIRouter()


# ============================================================================
# WEBHOOK MONITORING ENDPOINTS
# ============================================================================

@router.get("/webhooks/events", response_model=SuccessResponse[WebhookEventListResponse])
@require_permissions("subscription.manage", workspace_scoped=False)
@db_transaction_handler("get webhook events", auto_commit=False)
async def get_webhook_events(
    request: Request,
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(50, ge=1, le=200, description="Items per page"),
    event_name: Optional[str] = Query(None, description="Filter by event name"),
    processed: Optional[bool] = Query(None, description="Filter by processed status"),
    start_date: Optional[datetime] = Query(None, description="Start date filter"),
    end_date: Optional[datetime] = Query(None, description="End date filter"),
    include_payload: bool = Query(False, description="Include redacted payload body"),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    List recent webhook events (requires subscription.manage permission).

    Query Parameters:
    - page: Page number (default 1)
    - per_page: Items per page (default 50, max 200)
    - event_name: Filter by event name (e.g., "subscription_created")
    - processed: Filter by processing status (true/false)
    - start_date: Start date filter (ISO format)
    - end_date: End date filter (ISO format)

    Returns:
    - List of webhook events with details
    - Pagination metadata
    - Summary statistics
    """
    admin_user_id = current_user.get("identity")
    await require_super_admin(db, admin_user_id)

    # Build filters
    filters = []
    if event_name:
        filters.append(WebhookEvent.event_name == event_name)
    if processed is not None:
        filters.append(WebhookEvent.processed == processed)
    if start_date:
        filters.append(WebhookEvent.created_at >= start_date)
    if end_date:
        filters.append(WebhookEvent.created_at <= end_date)

    # Count total
    count_query = select(func.count(WebhookEvent.id))
    if filters:
        count_query = count_query.where(and_(*filters))
    total_result = await db.execute(count_query)
    total_events = total_result.scalar() or 0

    # Get paginated events
    offset = (page - 1) * per_page
    query = select(WebhookEvent)
    if filters:
        query = query.where(and_(*filters))
    query = query.order_by(desc(WebhookEvent.created_at)).offset(offset).limit(per_page)

    result = await db.execute(query)
    events = result.scalars().all()

    # Get summary statistics
    stats_query = select(
        func.count(WebhookEvent.id).label("total"),
        func.sum(func.cast(WebhookEvent.processed, Integer)).label("processed_count"),
        func.sum(func.cast(~WebhookEvent.processed, Integer)).label("pending_count"),
        func.sum(
            func.cast(
                and_(~WebhookEvent.processed, WebhookEvent.error_message.isnot(None)),
                Integer
            )
        ).label("failed_count"),
    )
    if filters:
        stats_query = stats_query.where(and_(*filters))

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
        data=result_data,
        request=request,
        message="Webhook events retrieved successfully"
    )


@router.get("/webhooks/failed", response_model=SuccessResponse[FailedWebhookListResponse])
@require_permissions("subscription.manage", workspace_scoped=False)
@db_transaction_handler("get failed webhook events", auto_commit=False)
async def get_failed_webhook_events(
    request: Request,
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(50, ge=1, le=200, description="Items per page"),
    hours: int = Query(24, ge=1, le=720, description="Look back hours (default 24, max 720/30 days)"),
    include_payload: bool = Query(False, description="Include redacted payload body"),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    List failed webhook events (requires subscription.manage permission).

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
        WebhookEvent.processed == False,
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
        failure_stats.append({
            "event_name": row.event_name,
            "failure_count": row.count,
            "max_retries": row.max_retries,
        })

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
        message=f"Failed webhook events from last {hours} hours retrieved successfully"
    )


@router.post("/webhooks/{event_id}/retry", response_model=SuccessResponse[WebhookRetryResponse])
@require_permissions("subscription.manage", workspace_scoped=False)
@db_transaction_handler("retry failed webhook")
async def retry_failed_webhook(
    request: Request,
    event_id: str,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Retry a failed webhook event (requires subscription.manage permission).

    This endpoint marks a failed webhook event for reprocessing.
    The actual reprocessing happens via the webhook processor service.

    Path Parameters:
    - event_id: The LemonSqueezy event ID to retry

    Returns:
    - Updated webhook event details
    """
    admin_user_id = current_user.get("identity")
    await require_super_admin(db, admin_user_id)

    # Find the webhook event
    query = select(WebhookEvent).where(WebhookEvent.event_id == event_id)
    result = await db.execute(query)
    webhook_event = result.scalar_one_or_none()

    if not webhook_event:
        result_data = {
            "success": False,
            "data": None,
        }
        return success(
            data=result_data,
            request=request,
            message=f"Webhook event {event_id} not found",
        )

    # Check if already processed successfully
    if webhook_event.processed and not webhook_event.error_message:
        result_data = {
            "success": False,
            "data": webhook_event.to_dict(),
        }
        return success(
            data=result_data,
            request=request,
            message="Webhook event already processed successfully - no retry needed",
        )

    # Mark for retry by resetting processed flag and incrementing retry count
    webhook_event.processed = False
    webhook_event.error_message = None  # Clear error to allow retry
    webhook_event.retry_count += 1
    webhook_event.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(webhook_event)

    result_data = {
        "success": True,
        "data": webhook_event.to_dict(),
    }
    return success(
        data=result_data,
        request=request,
        message=f"Webhook event {event_id} marked for retry (attempt {webhook_event.retry_count})",
    )


@router.get("/webhooks/stats", response_model=SuccessResponse[WebhookStatisticsResponse])
@require_permissions("subscription.manage", workspace_scoped=False)
@db_transaction_handler("get webhook statistics", auto_commit=False)
async def get_webhook_statistics(
    request: Request,
    days: int = Query(7, ge=1, le=90, description="Look back days (default 7, max 90)"),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get webhook processing statistics (requires subscription.manage permission).

    Query Parameters:
    - days: Look back period in days (default 7, max 90)

    Returns:
    - Processing statistics by event type
    - Success/failure rates
    - Processing time metrics
    """
    admin_user_id = current_user.get("identity")
    await require_super_admin(db, admin_user_id)

    # Calculate time filter
    since_date = datetime.now(timezone.utc) - timedelta(days=days)

    # Get overall statistics
    overall_query = select(
        func.count(WebhookEvent.id).label("total"),
        func.sum(func.cast(WebhookEvent.processed, Integer)).label("processed"),
        func.sum(
            func.cast(
                and_(~WebhookEvent.processed, WebhookEvent.error_message.isnot(None)),
                Integer
            )
        ).label("failed"),
        func.avg(WebhookEvent.retry_count).label("avg_retries"),
    ).where(WebhookEvent.created_at >= since_date)

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
            func.sum(func.cast(WebhookEvent.processed, Integer)).label("processed"),
            func.sum(
                func.cast(
                    and_(~WebhookEvent.processed, WebhookEvent.error_message.isnot(None)),
                    Integer
                )
            ).label("failed"),
        )
        .where(WebhookEvent.created_at >= since_date)
        .group_by(WebhookEvent.event_name)
        .order_by(desc(func.count(WebhookEvent.id)))
    )

    by_type_result = await db.execute(by_type_query)
    by_type_stats = []
    for row in by_type_result.all():
        total = row.total or 0
        processed = row.processed or 0
        failed = row.failed or 0
        success_rate_type = (processed / total * 100) if total > 0 else 0

        by_type_stats.append({
            "event_name": row.event_name,
            "total": total,
            "processed": processed,
            "failed": failed,
            "success_rate": round(success_rate_type, 2),
        })

    result_data = {
        "period": {
            "days": days,
            "since": since_date.isoformat(),
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
    return success(
        data=result_data,
        request=request,
        message=f"Webhook statistics for last {days} days retrieved successfully"
    )
