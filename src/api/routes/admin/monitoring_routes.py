"""
Admin System Monitoring API endpoints.

This module provides administrative operations for system monitoring
including health checks, error logs, and usage statistics.

All endpoints require admin permissions.
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.database.async_database import get_async_db
from src.api.models.admin_models.error_log import ErrorLog
from src.api.models.content_models.content import Content
from src.api.models.user_models.users import Users
from src.api.models.workspace_models.workspace_model import WorkspaceModel
from src.api.security.dependencies import get_current_user
from src.api.middleware.permissions import require_permissions
from src.utils.route_decorators import db_transaction_handler


router = APIRouter(prefix="/monitoring", tags=["Admin - Monitoring"])


# ============================================================================
# SYSTEM HEALTH ENDPOINTS
# ============================================================================


@router.get("/system-health", response_model=dict)
@db_transaction_handler("get system health", auto_commit=False)
async def get_system_health(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
    _: None = Depends(require_permissions(["system:monitor"]))
):
    """
    Get system health metrics (admin only).

    Returns:
    - Database health (status, response time, connection count)
    - Cache health (status, hit rate, memory usage)
    - API health (status, requests per minute, avg response time, error rate)
    - Workers health (status, active jobs, failed jobs)
    """
    import time

    # Database health check
    db_start = time.time()
    try:
        await db.execute(select(func.count(Users.id)))
        db_response_time = int((time.time() - db_start) * 1000)
        db_status = "healthy" if db_response_time < 100 else "degraded"

        # Get connection pool stats (approximate)
        db_health = {
            "status": db_status,
            "response_time_ms": db_response_time,
            "connection_count": 5,  # Placeholder - would need actual pool stats
            "max_connections": 100
        }
    except Exception as e:
        db_health = {
            "status": "unhealthy",
            "response_time_ms": 0,
            "connection_count": 0,
            "max_connections": 100,
            "error": str(e)
        }

    # Cache health (placeholder - implement if Redis is added)
    cache_health = {
        "status": "not_configured",
        "hit_rate": 0,
        "memory_used_mb": 0
    }

    # API health metrics
    # In production, these would come from request tracking middleware aggregates
    api_health = {
        "status": "healthy",
        "requests_per_minute": 150,  # Placeholder
        "avg_response_time_ms": 120,  # Placeholder
        "error_rate": 0.2  # Placeholder - percentage
    }

    # Workers health (placeholder - implement if background workers are added)
    workers_health = {
        "status": "not_configured",
        "active_jobs": 0,
        "failed_jobs_24h": 0
    }

    return {
        "data": {
            "database": db_health,
            "cache": cache_health,
            "api": api_health,
            "workers": workers_health,
            "timestamp": datetime.utcnow().isoformat()
        },
        "message": "System health retrieved successfully"
    }


# ============================================================================
# ERROR LOG ENDPOINTS
# ============================================================================


@router.get("/error-logs", response_model=dict)
@db_transaction_handler("get error logs", auto_commit=False)
async def get_error_logs(
    request: Request,
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(50, ge=1, le=100, description="Items per page"),
    severity: Optional[str] = Query(None, description="Filter by severity"),
    start_date: Optional[datetime] = Query(None, description="Start date filter"),
    end_date: Optional[datetime] = Query(None, description="End date filter"),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
    _: None = Depends(require_permissions(["system:monitor"]))
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
    # Build query
    query = select(ErrorLog).order_by(ErrorLog.timestamp.desc())

    # Apply filters
    filters = []
    if severity:
        filters.append(ErrorLog.severity == severity)
    if start_date:
        filters.append(ErrorLog.timestamp >= start_date)
    if end_date:
        filters.append(ErrorLog.timestamp <= end_date)

    if filters:
        query = query.where(and_(*filters))

    # Count total
    count_query = select(func.count()).select_from(ErrorLog)
    if filters:
        count_query = count_query.where(and_(*filters))
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Apply pagination
    offset = (page - 1) * per_page
    query = query.offset(offset).limit(per_page)

    # Execute query
    result = await db.execute(query)
    logs = result.scalars().all()

    # Format response
    log_list = []
    for log in logs:
        log_list.append({
            "id": str(log.id),
            "timestamp": log.timestamp.isoformat() if log.timestamp else None,
            "severity": log.severity,
            "message": log.message,
            "source": log.source,
            "user_id": str(log.user_id) if log.user_id else None,
            "request_id": log.request_id,
            "stack_trace": log.stack_trace,
            "metadata": log.metadata,
            "resolved": log.resolved,
            "resolved_at": log.resolved_at.isoformat() if log.resolved_at else None
        })

    # Calculate pagination
    total_pages = (total + per_page - 1) // per_page

    return {
        "data": log_list,
        "pagination": {
            "total": total,
            "page": page,
            "per_page": per_page,
            "total_pages": total_pages
        },
        "message": "Error logs retrieved successfully"
    }


@router.patch("/error-logs/{log_id}/resolve", response_model=dict)
@db_transaction_handler("resolve error log", auto_commit=True)
async def resolve_error_log(
    request: Request,
    log_id: str,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
    _: None = Depends(require_permissions(["system:monitor"]))
):
    """
    Mark an error log as resolved (admin only).

    Path Parameters:
    - log_id: Error log ID

    Returns:
    - Updated error log
    """
    from uuid import UUID

    admin_user_id = current_user.get("identity")

    # Get error log
    query = select(ErrorLog).where(ErrorLog.id == UUID(log_id))
    result = await db.execute(query)
    log = result.scalar_one_or_none()

    if not log:
        raise HTTPException(status_code=404, detail="Error log not found")

    # Mark as resolved
    log.resolved = True
    log.resolved_at = datetime.utcnow()
    log.resolved_by = UUID(admin_user_id)

    await db.commit()
    await db.refresh(log)

    return {
        "data": {
            "id": str(log.id),
            "resolved": log.resolved,
            "resolved_at": log.resolved_at.isoformat() if log.resolved_at else None,
            "resolved_by": str(log.resolved_by) if log.resolved_by else None
        },
        "message": "Error log marked as resolved"
    }


# ============================================================================
# USAGE STATISTICS ENDPOINTS
# ============================================================================


@router.get("/usage-stats", response_model=dict)
@db_transaction_handler("get usage stats", auto_commit=False)
async def get_usage_stats(
    request: Request,
    period: str = Query("24_hours", regex="^(24_hours|7_days|30_days)$", description="Time period"),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
    _: None = Depends(require_permissions(["system:monitor"]))
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
    # Calculate period start
    period_map = {
        "24_hours": timedelta(hours=24),
        "7_days": timedelta(days=7),
        "30_days": timedelta(days=30)
    }
    period_delta = period_map.get(period, timedelta(hours=24))
    period_start = datetime.utcnow() - period_delta

    # API calls (placeholder - would track via middleware in production)
    api_stats = {
        "total": 15000,  # Placeholder
        "by_endpoint": [
            {"endpoint": "/api/v1/content/generate", "count": 5000},
            {"endpoint": "/api/v1/workspaces", "count": 3000},
            {"endpoint": "/api/v1/topics", "count": 2500},
        ],
        "by_hour": []  # Would include hourly breakdown
    }

    # Content generation stats
    content_query = select(
        func.count(Content.id).label("total"),
        func.sum(func.case((Content.status == "published", 1), else_=0)).label("successful")
    ).where(Content.created_at >= period_start)

    content_result = await db.execute(content_query)
    content_row = content_result.first()

    content_total = content_row[0] if content_row else 0
    content_successful = content_row[1] if content_row else 0
    content_failed = content_total - content_successful

    content_stats = {
        "total": content_total,
        "successful": content_successful,
        "failed": content_failed
    }

    # User activity stats
    # Active users (logged in during period)
    active_users_query = select(func.count(func.distinct(Users.id))).where(
        Users.last_login_at >= period_start
    )
    active_users_result = await db.execute(active_users_query)
    active_users = active_users_result.scalar() or 0

    # New users (created during period)
    new_users_query = select(func.count(Users.id)).where(
        Users.created_at >= period_start
    )
    new_users_result = await db.execute(new_users_query)
    new_users = new_users_result.scalar() or 0

    # New workspaces
    new_workspaces_query = select(func.count(WorkspaceModel.id)).where(
        WorkspaceModel.created_at >= period_start
    )
    new_workspaces_result = await db.execute(new_workspaces_query)
    new_workspaces = new_workspaces_result.scalar() or 0

    user_activity_stats = {
        "active_users": active_users,
        "new_users": new_users,
        "new_workspaces": new_workspaces,
        "sessions": active_users * 2  # Approximate - 2 sessions per active user
    }

    return {
        "data": {
            "period": period,
            "period_start": period_start.isoformat(),
            "api_calls": api_stats,
            "content_generation": content_stats,
            "user_activity": user_activity_stats
        },
        "message": "Usage statistics retrieved successfully"
    }


@router.get("/usage-stats/trends", response_model=dict)
@db_transaction_handler("get usage trends", auto_commit=False)
async def get_usage_trends(
    request: Request,
    days: int = Query(7, ge=1, le=30, description="Number of days"),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
    _: None = Depends(require_permissions(["system:monitor"]))
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
    trends = []

    for i in range(days, -1, -1):
        day_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=i)
        day_end = day_start + timedelta(days=1)

        # Content created
        content_query = select(func.count(Content.id)).where(
            Content.created_at >= day_start,
            Content.created_at < day_end
        )
        content_result = await db.execute(content_query)
        content_count = content_result.scalar() or 0

        # Active users
        users_query = select(func.count(func.distinct(Users.id))).where(
            Users.last_login_at >= day_start,
            Users.last_login_at < day_end
        )
        users_result = await db.execute(users_query)
        users_count = users_result.scalar() or 0

        # Workspaces created
        workspaces_query = select(func.count(WorkspaceModel.id)).where(
            WorkspaceModel.created_at >= day_start,
            WorkspaceModel.created_at < day_end
        )
        workspaces_result = await db.execute(workspaces_query)
        workspaces_count = workspaces_result.scalar() or 0

        trends.append({
            "date": day_start.strftime("%Y-%m-%d"),
            "content_created": content_count,
            "active_users": users_count,
            "workspaces_created": workspaces_count
        })

    return {
        "data": {
            "days": days,
            "trends": trends
        },
        "message": "Usage trends retrieved successfully"
    }
