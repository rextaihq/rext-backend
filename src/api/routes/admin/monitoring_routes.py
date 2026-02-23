"""
Admin System Monitoring API endpoints.

This module provides administrative operations for system monitoring
including health checks, error logs, and usage statistics.

All endpoints require admin permissions.
"""

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.database.async_database import get_async_db
from src.api.security.dependencies import get_current_user
from src.services.monitoring_service import MonitoringService
from src.utils.route_decorators import db_transaction_handler, require_permissions


router = APIRouter(prefix="/monitoring", tags=["Admin - Monitoring"])


# ============================================================================
# SYSTEM HEALTH ENDPOINTS
# ============================================================================


@router.get("/system-health", response_model=dict)
@db_transaction_handler("get system health", auto_commit=False)
@require_permissions("audit.read", workspace_scoped=False)
async def get_system_health(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get system health metrics (admin only).

    Returns:
    - Database health (status, response time, connection count)
    - Cache health (status, hit rate, memory usage)
    - API health (status, requests per minute, avg response time, error rate)
    - Workers health (status, active jobs, failed jobs)
    """
    # Use service
    service = MonitoringService(db)
    health_data = await service.get_system_health()

    return {
        "data": health_data,
        "message": "System health retrieved successfully"
    }


# ============================================================================
# ERROR LOG ENDPOINTS
# ============================================================================


@router.get("/error-logs", response_model=dict)
@require_permissions("audit.read", workspace_scoped=False)
@db_transaction_handler("get error logs", auto_commit=False)
async def get_error_logs(
    request: Request,
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(50, ge=1, le=100, description="Items per page"),
    severity: Optional[str] = Query(None, description="Filter by severity"),
    start_date: Optional[datetime] = Query(None, description="Start date filter"),
    end_date: Optional[datetime] = Query(None, description="End date filter"),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get application error logs (admin only).

    Query Parameters:
    - page: Page number (default 1)
    - per_page: Items per page (default 50, max 100)
    - severity: Filter by severity (error, warning, critical)
    - start_date: Start date filter (ISO format)
    - end_date: End date filter (ISO format)

    Returns:
    - List of error logs with details
    - Pagination metadata
    """
    # Use service
    service = MonitoringService(db)
    result = await service.get_error_logs(
        page=page,
        per_page=per_page,
        severity=severity,
        start_date=start_date,
        end_date=end_date
    )

    return {
        "data": result["logs"],
        "pagination": result["pagination"],
        "message": "Error logs retrieved successfully"
    }


@router.patch("/error-logs/{log_id}/resolve", response_model=dict)
@require_permissions("audit.read", workspace_scoped=False)
@db_transaction_handler("resolve error log", auto_commit=True)
async def resolve_error_log(
    request: Request,
    log_id: str,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Mark an error log as resolved (admin only).

    Path Parameters:
    - log_id: Error log ID

    Returns:
    - Updated error log
    """
    admin_user_id = current_user.get("identity")

    # Use service
    service = MonitoringService(db)
    log_data = await service.resolve_error_log(
        log_id=UUID(log_id),
        admin_user_id=UUID(admin_user_id)
    )

    return {
        "data": log_data,
        "message": "Error log marked as resolved"
    }


# ============================================================================
# USAGE STATISTICS ENDPOINTS
# ============================================================================


@router.get("/usage-stats", response_model=dict)
@db_transaction_handler("get usage stats", auto_commit=False)
@require_permissions("audit.read", workspace_scoped=False)
async def get_usage_stats(
    request: Request,
    period: str = Query("24_hours", pattern="^(24_hours|7_days|30_days)$", description="Time period"),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get platform usage statistics (admin only).

    Query Parameters:
    - period: 24_hours, 7_days, or 30_days (default 24_hours)

    Returns:
    - API call statistics
    - Content generation statistics
    - User activity statistics
    """
    # Use service
    service = MonitoringService(db)
    stats_data = await service.get_usage_stats(period=period)

    return {
        "data": stats_data,
        "message": "Usage statistics retrieved successfully"
    }


@router.get("/usage-stats/trends", response_model=dict)
@db_transaction_handler("get usage trends", auto_commit=False)
@require_permissions("audit.read", workspace_scoped=False)
async def get_usage_trends(
    request: Request,
    days: int = Query(7, ge=1, le=30, description="Number of days"),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get usage trends over time (admin only).

    Query Parameters:
    - days: Number of days to analyze (default 7, max 30)

    Returns:
    - Daily content creation trends
    - Daily user activity trends
    - Daily workspace creation trends
    """
    # Use service
    service = MonitoringService(db)
    trends_data = await service.get_usage_trends(days=days)

    return {
        "data": trends_data,
        "message": "Usage trends retrieved successfully"
    }
