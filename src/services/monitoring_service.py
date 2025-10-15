"""
Monitoring Service - Business Logic for System Monitoring

This service encapsulates all business logic related to system monitoring,
error logging, and usage statistics.

Responsibilities:
- System health checks
- Error log management
- Usage statistics aggregation
- Trend analysis

Does NOT:
- Handle HTTP requests/responses (that's routes)
- Commit transactions (that's decorators)
- Check authentication (that's decorators)
"""

import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.models.admin_models.error_log import ErrorLog
from src.api.models.content_models.content import Content
from src.api.models.user_models.users import Users
from src.api.models.workspace_models.workspace_model import WorkspaceModel
from src.api.middleware.exceptions import ResourceNotFoundException
from src.utils.logger import logger


class MonitoringService:
    """Service for system monitoring operations"""

    def __init__(self, db: AsyncSession):
        """
        Initialize MonitoringService.

        Args:
            db: Async database session
        """
        self.db = db

    async def get_system_health(self) -> Dict[str, Any]:
        """
        Get system health metrics.

        Returns:
            Dict with database, cache, API, and workers health
        """
        # Database health check
        db_start = time.time()
        try:
            await self.db.execute(select(func.count(Users.id)))
            db_response_time = int((time.time() - db_start) * 1000)
            db_status = "healthy" if db_response_time < 100 else "degraded"

            db_health = {
                "status": db_status,
                "response_time_ms": db_response_time,
                "connection_count": 5,  # Placeholder
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

        # API health metrics (placeholder)
        api_health = {
            "status": "healthy",
            "requests_per_minute": 150,
            "avg_response_time_ms": 120,
            "error_rate": 0.2
        }

        # Workers health (placeholder)
        workers_health = {
            "status": "not_configured",
            "active_jobs": 0,
            "failed_jobs_24h": 0
        }

        logger.info("System health metrics retrieved")

        return {
            "database": db_health,
            "cache": cache_health,
            "api": api_health,
            "workers": workers_health,
            "timestamp": datetime.utcnow().isoformat()
        }

    async def get_error_logs(
        self,
        page: int = 1,
        per_page: int = 50,
        severity: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Get error logs with filtering and pagination.

        Args:
            page: Page number
            per_page: Items per page
            severity: Filter by severity
            start_date: Start date filter
            end_date: End date filter

        Returns:
            Dict with error logs and pagination metadata
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
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        # Apply pagination
        offset = (page - 1) * per_page
        query = query.offset(offset).limit(per_page)

        # Execute query
        result = await self.db.execute(query)
        logs = result.scalars().all()

        # Format response
        log_list = [
            {
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
            }
            for log in logs
        ]

        # Calculate pagination
        total_pages = (total + per_page - 1) // per_page

        logger.info(f"Retrieved {len(log_list)} error logs (page {page}/{total_pages})")

        return {
            "logs": log_list,
            "pagination": {
                "total": total,
                "page": page,
                "per_page": per_page,
                "total_pages": total_pages
            }
        }

    async def resolve_error_log(
        self,
        log_id: UUID,
        admin_user_id: UUID
    ) -> Dict[str, Any]:
        """
        Mark error log as resolved.

        Args:
            log_id: Error log UUID
            admin_user_id: Admin user UUID

        Returns:
            Dict with updated error log

        Raises:
            ResourceNotFoundException: If log not found
        """
        query = select(ErrorLog).where(ErrorLog.id == log_id)
        result = await self.db.execute(query)
        log = result.scalar_one_or_none()

        if not log:
            raise ResourceNotFoundException(
                resource_type="ErrorLog",
                resource_id=str(log_id)
            )

        # Mark as resolved
        log.resolved = True
        log.resolved_at = datetime.utcnow()
        log.resolved_by = admin_user_id

        logger.info(f"Error log {log_id} marked as resolved by admin {admin_user_id}")

        return {
            "id": str(log.id),
            "resolved": log.resolved,
            "resolved_at": log.resolved_at.isoformat() if log.resolved_at else None,
            "resolved_by": str(log.resolved_by) if log.resolved_by else None
        }

    async def get_usage_stats(self, period: str = "24_hours") -> Dict[str, Any]:
        """
        Get platform usage statistics.

        Args:
            period: Time period (24_hours, 7_days, 30_days)

        Returns:
            Dict with API calls, content generation, and user activity stats
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
            "total": 15000,
            "by_endpoint": [
                {"endpoint": "/api/v1/content/generate", "count": 5000},
                {"endpoint": "/api/v1/workspaces", "count": 3000},
                {"endpoint": "/api/v1/topics", "count": 2500},
            ],
            "by_hour": []
        }

        # Content generation stats
        content_query = select(
            func.count(Content.id).label("total"),
            func.sum(func.case((Content.status == "published", 1), else_=0)).label("successful")
        ).where(Content.created_at >= period_start)

        content_result = await self.db.execute(content_query)
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
        active_users_query = select(func.count(func.distinct(Users.id))).where(
            Users.last_login_at >= period_start
        )
        active_users_result = await self.db.execute(active_users_query)
        active_users = active_users_result.scalar() or 0

        new_users_query = select(func.count(Users.id)).where(
            Users.created_at >= period_start
        )
        new_users_result = await self.db.execute(new_users_query)
        new_users = new_users_result.scalar() or 0

        new_workspaces_query = select(func.count(WorkspaceModel.id)).where(
            WorkspaceModel.created_at >= period_start
        )
        new_workspaces_result = await self.db.execute(new_workspaces_query)
        new_workspaces = new_workspaces_result.scalar() or 0

        user_activity_stats = {
            "active_users": active_users,
            "new_users": new_users,
            "new_workspaces": new_workspaces,
            "sessions": active_users * 2  # Approximate
        }

        logger.info(f"Usage stats retrieved for period: {period}")

        return {
            "period": period,
            "period_start": period_start.isoformat(),
            "api_calls": api_stats,
            "content_generation": content_stats,
            "user_activity": user_activity_stats
        }

    async def get_usage_trends(self, days: int = 7) -> Dict[str, Any]:
        """
        Get usage trends over time.

        Args:
            days: Number of days to analyze

        Returns:
            Dict with daily trends
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
            content_result = await self.db.execute(content_query)
            content_count = content_result.scalar() or 0

            # Active users
            users_query = select(func.count(func.distinct(Users.id))).where(
                Users.last_login_at >= day_start,
                Users.last_login_at < day_end
            )
            users_result = await self.db.execute(users_query)
            users_count = users_result.scalar() or 0

            # Workspaces created
            workspaces_query = select(func.count(WorkspaceModel.id)).where(
                WorkspaceModel.created_at >= day_start,
                WorkspaceModel.created_at < day_end
            )
            workspaces_result = await self.db.execute(workspaces_query)
            workspaces_count = workspaces_result.scalar() or 0

            trends.append({
                "date": day_start.strftime("%Y-%m-%d"),
                "content_created": content_count,
                "active_users": users_count,
                "workspaces_created": workspaces_count
            })

        logger.info(f"Usage trends retrieved for {days} days")

        return {
            "days": days,
            "trends": trends
        }
