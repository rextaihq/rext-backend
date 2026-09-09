"""
Admin Webhook Monitoring API endpoints.

This module provides administrative webhook monitoring operations including:
- List recent webhook events
- Get failed webhook events
- Retry failed webhooks
- Get webhook statistics

All endpoints require the `audit.read` permission (platform admin monitoring).

DEPRECATED: This router is superseded by
``/api/v1/admin/subscriptions/webhooks/*`` (see
``src/api/routes/subscriptions/admin/webhook_monitoring_routes.py``), which is
the single source of truth consumed by the admin dashboard. These endpoints are
retained temporarily for backward compatibility and will be removed. Both
implementations read/write the same ``webhook_events`` table and now share the
same retry/reprocessing logic via ``WebhookMonitoringService``.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.database.async_database import get_async_db
from src.api.schema.response_schemas import SuccessResponse
from src.api.schema.webhook_monitoring_schema import (
    WebhookEventsResponseSchema,
    WebhookRetryResponseSchema,
    WebhookStatsResponseSchema,
)
from src.api.security.dependencies import get_current_user
from src.services.webhook_monitoring_service import WebhookMonitoringService
from src.utils.response_utils import success
from src.utils.route_decorators import db_transaction_handler, require_permissions

router = APIRouter()


# ============================================================================
# WEBHOOK MONITORING ENDPOINTS
# ============================================================================


@router.get(
    "/webhooks/events", response_model=SuccessResponse[WebhookEventsResponseSchema], deprecated=True
)
@require_permissions("audit.read", workspace_scoped=False)
@db_transaction_handler("get webhook events", auto_commit=False)
async def get_webhook_events(
    request: Request,
    limit: int = Query(50, ge=1, le=100, description="Maximum events to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    event_name: str = Query(None, description="Filter by event name"),
    processed: bool = Query(None, description="Filter by processed status"),
    hours: int = Query(None, ge=1, le=720, description="Only show events from last N hours"),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Get webhook events with filtering and pagination (requires audit.read).

    Query Parameters:
    - limit: Maximum number of events (default 50, max 100)
    - offset: Pagination offset (default 0)
    - event_name: Filter by specific event name
    - processed: Filter by processed status (true/false)
    - hours: Only show events from last N hours

    Returns:
    - List of webhook events with metadata
    - Total count for pagination
    """
    service = WebhookMonitoringService(db)
    result = await service.get_webhook_events(
        limit=limit, offset=offset, event_name=event_name, processed=processed, hours=hours
    )
    # Normalize to consistent pagination shape
    return success(
        data={
            "items": result.get("events", []),
            "total": result.get("total", 0),
            "limit": limit,
            "offset": offset,
            "has_more": (offset + limit) < result.get("total", 0),
        },
        request=request,
        message="Webhook events retrieved successfully",
    )


@router.get(
    "/webhooks/failed", response_model=SuccessResponse[WebhookEventsResponseSchema], deprecated=True
)
@require_permissions("audit.read", workspace_scoped=False)
@db_transaction_handler("get failed webhooks", auto_commit=False)
async def get_failed_webhooks(
    request: Request,
    limit: int = Query(50, ge=1, le=100, description="Maximum events to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    hours: int = Query(24, ge=1, le=720, description="Only show events from last N hours"),
    include_payload: bool = Query(
        False, description="Include redacted payload body in response (default false)"
    ),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Get failed webhook events (requires audit.read).

    Query Parameters:
    - limit: Maximum number of events (default 50, max 100)
    - offset: Pagination offset (default 0)
    - hours: Only show events from last N hours (default 24)
    - include_payload: Include redacted payload body

    Returns:
    - List of failed webhook events with redacted payload (if requested)
    """
    service = WebhookMonitoringService(db)
    result = await service.get_failed_webhooks(
        limit=limit, offset=offset, hours=hours, include_payload=include_payload
    )
    return success(
        data={
            "items": result.get("events", []),
            "total": result.get("total", 0),
            "limit": limit,
            "offset": offset,
            "has_more": (offset + limit) < result.get("total", 0),
        },
        request=request,
        message="Failed webhook events retrieved successfully",
    )


@router.post(
    "/webhooks/{webhook_id}/retry",
    response_model=SuccessResponse[WebhookRetryResponseSchema],
    deprecated=True,
)
@require_permissions("audit.read", workspace_scoped=False)
@db_transaction_handler("retry webhook", auto_commit=True)
async def retry_webhook(
    request: Request,
    webhook_id: UUID = Path(..., description="Webhook event ID to retry"),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Retry processing a failed webhook event (requires audit.read).

    Path Parameters:
    - webhook_id: ID of the webhook event to retry

    Returns:
    - Success status and updated event details

    Notes:
    - Only unprocessed webhooks can be retried
    - Retry count is incremented
    - Error messages are updated if retry fails
    """
    service = WebhookMonitoringService(db)
    result = await service.retry_webhook(webhook_id)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("message", "Retry failed"))
    return success(
        data={"event": result.get("event")}, request=request, message="Webhook retried successfully"
    )


@router.get(
    "/webhooks/statistics",
    response_model=SuccessResponse[WebhookStatsResponseSchema],
    deprecated=True,
)
@require_permissions("audit.read", workspace_scoped=False)
@db_transaction_handler("get webhook statistics", auto_commit=False)
async def get_webhook_statistics(
    request: Request,
    hours: int = Query(24, ge=1, le=720, description="Statistics period in hours"),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Get webhook processing statistics (requires audit.read).

    Query Parameters:
    - hours: Statistics for last N hours (default 24)

    Returns:
    - Total events count
    - Processed, failed, and pending counts
    - Success rate percentage
    - Breakdown by event type
    - Recent errors for troubleshooting
    """
    service = WebhookMonitoringService(db)
    stats = await service.get_webhook_statistics(hours=hours)
    return success(data=stats, request=request, message="Webhook statistics retrieved successfully")
