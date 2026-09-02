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

import re
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import and_, func, select, case
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.models.admin_models.error_log import ErrorLog, ErrorLogSeverity
from src.api.models.content_models.content import Content
from src.api.models.user_models.users import Users
from src.api.models.workspace_models.workspace_model import WorkspaceModel
from src.api.middleware.exceptions import ResourceNotFoundException
from src.utils.logger import logger


class MonitoringService:
    """Service for system monitoring operations"""

    _SENSITIVE_TEXT_PATTERNS = [
        re.compile(r"(?i)(authorization\s*:\s*bearer\s+)[^\s]+"),
        re.compile(r"(?i)(api[_-]?key\s*[=:]\s*)[^\s,;]+"),
        re.compile(r"(?i)(password\s*[=:]\s*)[^\s,;]+"),
        re.compile(r"(?i)(secret\s*[=:]\s*)[^\s,;]+"),
    ]

    def __init__(self, db: AsyncSession):
        """
        Initialize MonitoringService.

        Args:
            db: Async database session
        """
        self.db = db

    def _redact_text(self, value: Optional[str]) -> Optional[str]:
        """Redact sensitive patterns from text and truncate if too long."""
        if value is None:
            return None

        redacted = value
        for pattern in self._SENSITIVE_TEXT_PATTERNS:
            redacted = pattern.sub(r"\1[REDACTED]", redacted)

        # Keep payloads bounded for API responses
        if len(redacted) > 4000:
            return redacted[:4000] + "\n...[truncated]"
        return redacted

    def _redact_json(self, obj: Any) -> Any:
        """Recursively redact sensitive keys in JSON-like objects."""
        sensitive_keys = {
            "authorization", "api_key", "apikey", "password", "secret", "token",
            "access_token", "refresh_token", "client_secret"
        }

        if isinstance(obj, dict):
            result = {}
            for key, value in obj.items():
                if key.lower() in sensitive_keys:
                    result[key] = "[REDACTED]"
                else:
                    result[key] = self._redact_json(value)
            return result

        if isinstance(obj, list):
            return [self._redact_json(item) for item in obj]

        if isinstance(obj, str):
            return self._redact_text(obj)

        return obj

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

            # Get real pool statistics from the async engine
            from src.api.database.async_database import async_engine
            pool = async_engine.pool
            db_health = {
                "status": db_status,
                "response_time_ms": db_response_time,
                "connection_count": pool.checkedin() + pool.checkedout(),
                "connections_checked_in": pool.checkedin(),
                "connections_checked_out": pool.checkedout(),
                "pool_overflow": pool.overflow(),
                "pool_size": pool.size(),
                "max_overflow": async_engine.pool._max_overflow,
                "max_connections": pool.size() + async_engine.pool._max_overflow,
            }
        except Exception as e:
            db_health = {
                "status": "unhealthy",
                "response_time_ms": 0,
                "connection_count": 0,
                "max_connections": 0,
                "error": str(e)
            }

        # Cache health check
        try:
            from src.api.cache.redis_client import cache
            cache_health = await cache.get_stats()
            if cache_health.get("enabled"):
                cache_health["status"] = "healthy"
            else:
                cache_health["status"] = "disabled"
        except Exception as e:
            cache_health = {
                "status": "unhealthy",
                "enabled": False,
                "error": str(e)
            }

        try:
            from src.api.cache.redis_client import cache as redis_cache
            redis = redis_cache.redis
            if redis is not None:
                now_ts = int(time.time())
                current_minute = now_ts - (now_ts % 60)

                # Get last 5 minutes of data for rolling averages
                total_requests = 0
                total_time = 0
                total_errors = 0
                minutes_with_data = 0

                pipe = redis.pipeline()
                for i in range(5):
                    bucket = current_minute - (i * 60)
                    pipe.get(f"metrics:api:count:{bucket}")
                    pipe.get(f"metrics:api:time_sum:{bucket}")
                    pipe.get(f"metrics:api:errors:{bucket}")
                results = await pipe.execute()

                for i in range(5):
                    count = int(results[i * 3] or 0)
                    time_sum = float(results[i * 3 + 1] or 0)
                    errors = int(results[i * 3 + 2] or 0)
                    if count > 0:
                        total_requests += count
                        total_time += time_sum
                        total_errors += errors
                        minutes_with_data += 1

                avg_rpm = total_requests / max(minutes_with_data, 1)
                avg_response_time = total_time / max(total_requests, 1)
                error_rate = (total_errors / max(total_requests, 1)) * 100

                api_status = "healthy"
                if error_rate > 10:
                    api_status = "degraded"
                if error_rate > 50:
                    api_status = "unhealthy"

                api_health = {
                    "status": api_status,
                    "requests_per_minute": round(avg_rpm, 1),
                    "avg_response_time_ms": round(avg_response_time, 1),
                    "error_rate": round(error_rate, 2),
                    "sample_window_minutes": minutes_with_data,
                }
            else:
                api_health = {
                    "status": "unknown",
                    "requests_per_minute": 0,
                    "avg_response_time_ms": 0,
                    "error_rate": 0,
                    "note": "Redis unavailable — API metrics not tracked"
                }
        except Exception as e:
            api_health = {
                "status": "unknown",
                "error": str(e)
            }

        # Workers health — background job queue not implemented
        workers_health = {
            "status": "not_implemented",
            "note": "Background job monitoring not yet implemented"
        }

        logger.info("System health metrics retrieved")

        return {
            "database": db_health,
            "cache": cache_health,
            "api": api_health,
            "workers": workers_health,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    async def get_error_logs(
        self,
        page: int = 1,
        per_page: int = 50,
        severity: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        include_stack_trace: bool = False
    ) -> Dict[str, Any]:
        """
        Get error logs with filtering and pagination.

        Args:
            page: Page number
            per_page: Items per page
            severity: Filter by severity
            start_date: Start date filter
            end_date: End date filter
            include_stack_trace: Whether to include redacted stack traces

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
                "message": self._redact_text(log.message),
                "source": log.source,
                "user_id": str(log.user_id) if log.user_id else None,
                "request_id": log.request_id,
                "stack_trace": self._redact_text(log.stack_trace) if include_stack_trace else None,
                "metadata": self._redact_json(log.error_metadata or {}),
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
        log.resolved_at = datetime.now(timezone.utc)
        log.resolved_by = admin_user_id

        logger.info(f"Error log {log_id} marked as resolved by admin {admin_user_id}")

        return {
            "id": str(log.id),
            "resolved": log.resolved,
            "resolved_at": log.resolved_at.isoformat() if log.resolved_at else None,
            "resolved_by": str(log.resolved_by) if log.resolved_by else None
        }

    # Map the API-level ErrorSeverity strings onto the constrained
    # error_logs.severity enum. "low" is intentionally excluded — 404s,
    # validation errors and similar noise are not persisted.
    _API_SEVERITY_TO_ERROR_LOG = {
        "medium": ErrorLogSeverity.WARNING,
        "high": ErrorLogSeverity.ERROR,
        "critical": ErrorLogSeverity.CRITICAL,
    }

    @classmethod
    async def persist_error_log(
        cls,
        *,
        api_severity: str,
        message: str,
        source: Optional[str] = None,
        user_id: Optional[str] = None,
        request_id: Optional[str] = None,
        stack_trace: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Persist a single error to the ``error_logs`` table so it surfaces in the
        admin System Monitoring dashboard.

        Best-effort: any failure here is swallowed and logged as a warning so
        that error logging can never affect the request that triggered it.
        Opens its own short-lived session because the request's session is
        typically already broken/rolled back by the time an exception reaches
        the error handler.
        """
        severity = cls._API_SEVERITY_TO_ERROR_LOG.get((api_severity or "").lower())
        if severity is None:
            return

        try:
            from src.api.database.async_database import AsyncSessionLocal

            redactor = cls.__new__(cls)  # redaction helpers need no session

            parsed_user_id: Optional[UUID] = None
            if user_id:
                try:
                    parsed_user_id = UUID(str(user_id))
                except (ValueError, TypeError):
                    parsed_user_id = None

            entry = ErrorLog(
                severity=severity,
                message=(redactor._redact_text(message) or "")[:8000],
                source=source[:255] if source else None,
                user_id=parsed_user_id,
                request_id=str(request_id)[:100] if request_id else None,
                stack_trace=redactor._redact_text(stack_trace),
                error_metadata=redactor._redact_json(metadata or {}),
            )

            async with AsyncSessionLocal() as session:
                session.add(entry)
                await session.commit()
        except Exception as exc:  # noqa: BLE001 - never propagate
            logger.warning(f"Failed to persist error log: {exc}")

    async def _get_api_usage(self, period_start: datetime) -> Dict[str, Any]:
        """
        API usage for the window: durable rollup + the live Redis tail.

        Returns total, by_endpoint (top 10) and by_hour.
        """
        from src.api.models.admin_models.api_usage import ApiUsageHourly

        by_endpoint: Dict[str, int] = {}
        by_hour: Dict[str, int] = {}
        total = 0

        # 1. Durable history.
        try:
            rows = (await self.db.execute(
                select(
                    ApiUsageHourly.endpoint,
                    ApiUsageHourly.hour_bucket,
                    func.sum(ApiUsageHourly.request_count).label("n"),
                )
                .where(ApiUsageHourly.hour_bucket >= period_start)
                .group_by(ApiUsageHourly.endpoint, ApiUsageHourly.hour_bucket)
            )).all()
            for endpoint, hour, n in rows:
                n = int(n or 0)
                total += n
                by_endpoint[endpoint] = by_endpoint.get(endpoint, 0) + n
                key = hour.isoformat()
                by_hour[key] = by_hour.get(key, 0) + n
        except Exception:
            logger.warning("Could not read api_usage_hourly", exc_info=True)

        # 2. Live tail: minutes the rollup has not drained yet.
        try:
            from src.api.cache.redis_client import cache as redis_cache
            redis = redis_cache.redis
            if redis is not None:
                now_ts = int(time.time())
                newest = now_ts - (now_ts % 60)
                for i in range(180):
                    bucket = newest - (i * 60)
                    if bucket < period_start.timestamp():
                        break
                    counts = await redis.hgetall(f"metrics:api:endpoint:{bucket}")
                    if not counts:
                        continue
                    hour = datetime.fromtimestamp(bucket, tz=timezone.utc).replace(
                        minute=0, second=0, microsecond=0
                    ).isoformat()
                    for field, raw in counts.items():
                        n = int(raw or 0)
                        _, _, endpoint = str(field).partition(" ")
                        endpoint = endpoint or str(field)
                        total += n
                        by_endpoint[endpoint] = by_endpoint.get(endpoint, 0) + n
                        by_hour[hour] = by_hour.get(hour, 0) + n
        except Exception:
            logger.warning("Could not read live API metrics", exc_info=True)

        top = sorted(by_endpoint.items(), key=lambda kv: kv[1], reverse=True)[:10]
        return {
            "total": total,
            "by_endpoint": [{"endpoint": e, "count": c} for e, c in top],
            "by_hour": [
                {"hour": h, "count": c} for h, c in sorted(by_hour.items())
            ],
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
        period_start = datetime.now(timezone.utc) - period_delta

        # API usage.
        #
        # Durable history comes from api_usage_hourly (written by the rollup
        # task); the not-yet-drained minutes are added from Redis so the numbers
        # are current. Previously this summed Redis alone, whose keys expired
        # after an hour -- so "7 days" and "30 days" both reported roughly the
        # last hour, and widening the period could *lower* the total.
        api_stats = await self._get_api_usage(period_start)

        # Content generation stats
        content_query = select(
            func.coalesce(func.count(Content.id), 0).label("total"),
            func.coalesce(func.sum(case({Content.status == "published": 1}, else_=0)), 0).label("successful")
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
            day_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=i)
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
