"""
Admin Webhook Monitoring API endpoints.

This module provides administrative webhook monitoring operations including:
- List recent webhook events
- Get failed webhook events
- Retry failed webhooks
- Get webhook statistics

All endpoints require super admin permissions.
"""
from fastapi import APIRouter, Depends, Request, Query, Path, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.database.async_database import get_async_db
from src.api.security.dependencies import get_current_user
from src.services.webhook_monitoring_service import WebhookMonitoringService
from src.utils.route_decorators import db_transaction_handler, require_permissions


router = APIRouter()


# ============================================================================
# WEBHOOK MONITORING ENDPOINTS
# ============================================================================

@router.get("/webhooks/events", response_model=dict)
@db_transaction_handler("get webhook events", auto_commit=False)
@require_permissions("audit.webhooks", workspace_scoped=False)
async def get_webhook_events(
    request: Request,
    limit: int = Query(50, ge=1, le=100, description="Maximum events to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    event_name: str = Query(None, description="Filter by event name"),
    processed: bool = Query(None, description="Filter by processed status"),
    hours: int = Query(None, ge=1, le=720, description="Only show events from last N hours"),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get webhook events with filtering and pagination (super admin only).

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
    return await service.get_webhook_events(
        limit=limit,
        offset=offset,
        event_name=event_name,
        processed=processed,
        hours=hours
    )


@router.get("/webhooks/failed", response_model=dict)
@db_transaction_handler("get failed webhooks", auto_commit=False)
@require_permissions("audit.webhooks", workspace_scoped=False)
async def get_failed_webhooks(
    request: Request,
    limit: int = Query(50, ge=1, le=100, description="Maximum events to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    hours: int = Query(24, ge=1, le=720, description="Only show events from last N hours"),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get failed webhook events (super admin only).

    Query Parameters:
    - limit: Maximum number of events (default 50, max 100)
    - offset: Pagination offset (default 0)
    - hours: Only show events from last N hours (default 24)

    Returns:
    - List of failed webhook events with full payload for debugging
    """


    service = WebhookMonitoringService(db)
    return await service.get_failed_webhooks(
        limit=limit,
        offset=offset,
        hours=hours
    )


@router.post("/webhooks/{webhook_id}/retry", response_model=dict)
@db_transaction_handler("retry webhook", auto_commit=True)
@require_permissions("audit.webhooks", workspace_scoped=False)
async def retry_webhook(
    request: Request,
    webhook_id: str = Path(..., description="Webhook event ID to retry"),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Retry processing a failed webhook event (super admin only).

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

    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])

    return result


@router.get("/webhooks/statistics", response_model=dict)
@db_transaction_handler("get webhook statistics", auto_commit=False)
@require_permissions("audit.webhooks", workspace_scoped=False)
async def get_webhook_statistics(
    request: Request,
    hours: int = Query(24, ge=1, le=720, description="Statistics period in hours"),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get webhook processing statistics (super admin only).

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
    return await service.get_webhook_statistics(hours=hours)
