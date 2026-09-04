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
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
from uuid import UUID

from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.middleware.exceptions import ResourceNotFoundException
from src.api.models.admin_models.error_log import ErrorLog, ErrorLogSeverity
from src.api.models.content_models.content import Content
from src.api.models.user_models.users import Users
from src.api.models.workspace_models.workspace_model import WorkspaceModel
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

    # ------------------------------------------------------------------
    # Operational severity policy for the admin Error Logs tab.
    #
    # This is deliberately a different scale from ErrorSeverity on the API
    # response. ErrorSeverity answers "how badly is the caller affected?"; this
    # answers "how urgently must an operator act?". They are not the same
    # question -- a third-party integration failing is a shrug for the caller
    # (their request 502s, they retry) but a page for the operator (credentials
    # expired, quota exhausted, vendor outage).
    #
    # Deriving one from the other is what produced the previous behaviour,
    # where a genuine unhandled crash and a briefly unreachable WordPress site
    # both landed in "error" and were indistinguishable on the dashboard.
    # ------------------------------------------------------------------

    # Stored levels, lowest first. Used to compare against the configured floor.
    _ERROR_LOG_ORDER = (
        ErrorLogSeverity.WARNING,
        ErrorLogSeverity.ERROR,
        ErrorLogSeverity.CRITICAL,
    )

    # Fallback mapping for callers that supply only an API severity string.
    #
    # "low" maps to warning rather than being dropped. ErrorLogSeverity has no
    # level below warning, and treating that as "not storable" silently
    # discarded a whole class of real events -- resource-not-found and
    # rate-limit rejections among them, so a client hammering the API left no
    # trace. Storing them at the lowest available level is the honest reading
    # of a three-level column; ERROR_LOG_MIN_SEVERITY still filters them out
    # for anyone who wants a quieter table.
    _API_SEVERITY_TO_ERROR_LOG = {
        "low": ErrorLogSeverity.WARNING,
        "medium": ErrorLogSeverity.WARNING,
        "high": ErrorLogSeverity.ERROR,
        "critical": ErrorLogSeverity.CRITICAL,
    }

    # The floor is configured on the stored scale. The previous release
    # configured it on the API scale, so those values are still accepted and
    # normalised rather than failing a deploy on an existing .env.
    _FLOOR_ALIASES = {
        "medium": ErrorLogSeverity.WARNING,
        "high": ErrorLogSeverity.ERROR,
        "warning": ErrorLogSeverity.WARNING,
        "error": ErrorLogSeverity.ERROR,
        "critical": ErrorLogSeverity.CRITICAL,
    }

    @classmethod
    def _is_infrastructure_failure(cls, exception: Any) -> bool:
        """
        Our own infrastructure (database, cache) as opposed to a third party.

        DatabaseConnectionException subclasses RextExternalServiceException, so
        without this check Postgres being unreachable would be classified as a
        vendor problem.
        """
        from src.api.middleware.exceptions import DatabaseConnectionException

        return isinstance(exception, DatabaseConnectionException)

    @classmethod
    def _is_third_party_failure(cls, exception: Any) -> bool:
        """A dependency we do not run: WordPress, Shopify, email, AI providers."""
        from src.api.middleware.exceptions import RextExternalServiceException

        return isinstance(exception, RextExternalServiceException)

    @classmethod
    def _is_handled_type(cls, exception: Any) -> bool:
        """
        Whether the exception is one the application raises on purpose.

        Anything else reaching an error handler escaped every ``except`` in the
        codebase -- an unhandled crash, and therefore a bug rather than a
        condition someone anticipated.
        """
        from fastapi import HTTPException
        from fastapi.exceptions import RequestValidationError
        from pydantic import ValidationError

        from src.api.middleware.exceptions import RextAPIException

        return isinstance(
            exception,
            (RextAPIException, HTTPException, ValidationError, RequestValidationError),
        )

    @classmethod
    def classify_error_log_severity(
        cls,
        *,
        exception: Any = None,
        api_severity: Optional[str] = None,
        status_code: Optional[int] = None,
    ) -> Optional[ErrorLogSeverity]:
        """
        Decide the stored level for one error, or None if it is not storable.

        Rules are evaluated in order; the first match wins.

          CRITICAL  unhandled crash (a bug in our code)
                    third-party dependency failed (vendor, credentials, quota)
          ERROR     our own infrastructure degraded (database, cache)
                    any other 5xx
          WARNING   4xx -- the caller's request was rejected as intended
        """
        if exception is not None:
            # Infrastructure is checked before third party because
            # DatabaseConnectionException subclasses the external-service type.
            if cls._is_infrastructure_failure(exception):
                return ErrorLogSeverity.ERROR
            if cls._is_third_party_failure(exception):
                return ErrorLogSeverity.CRITICAL
            if not cls._is_handled_type(exception):
                return ErrorLogSeverity.CRITICAL

        if status_code is not None and status_code >= 500:
            return ErrorLogSeverity.ERROR

        severity = (api_severity or "").lower()
        if severity in cls._API_SEVERITY_TO_ERROR_LOG:
            return cls._API_SEVERITY_TO_ERROR_LOG[severity]

        # An unrecognised value is a wiring mistake and is reported rather than
        # silently dropped.
        if severity:
            logger.warning(
                "Unknown error severity; not persisting",
                extra={"severity": api_severity},
            )
        return None

    @classmethod
    def _floor(cls) -> ErrorLogSeverity:
        from src.api.config import get_settings

        configured = (get_settings().ERROR_LOG_MIN_SEVERITY or "").lower()
        return cls._FLOOR_ALIASES.get(configured, ErrorLogSeverity.WARNING)

    @classmethod
    def is_path_excluded(cls, path: str = "") -> bool:
        from src.api.config import get_settings

        excluded = tuple(get_settings().ERROR_LOG_EXCLUDED_PATH_PREFIXES or ())
        return bool(excluded and path and path.startswith(excluded))

    @classmethod
    def resolve_error_log_severity(
        cls,
        *,
        exception: Any = None,
        api_severity: Optional[str] = None,
        status_code: Optional[int] = None,
        path: str = "",
    ) -> Optional[ErrorLogSeverity]:
        """
        Single decision point: the level to store, or None to skip.

        This used to be decided independently at three call sites with three
        different thresholds, which is why error_logs stayed empty while errors
        were plainly occurring. Centralising it means the paths cannot drift
        apart again.
        """
        if cls.is_path_excluded(path):
            return None

        severity = cls.classify_error_log_severity(
            exception=exception, api_severity=api_severity, status_code=status_code
        )
        if severity is None:
            return None

        if cls._ERROR_LOG_ORDER.index(severity) < cls._ERROR_LOG_ORDER.index(cls._floor()):
            return None
        return severity

    @classmethod
    def should_persist_error(cls, api_severity: Optional[str], path: str = "") -> bool:
        """Backwards-compatible gate for callers that have only a severity string."""
        return (
            cls.resolve_error_log_severity(api_severity=api_severity, path=path)
            is not None
        )

    # Last time each dependency's failure was recorded, keyed by name. A
    # dependency that is down fails on every request, so without throttling the
    # outage would write one row per request and bury every other error on the
    # dashboard under its own noise.
    _dependency_last_reported: Dict[str, float] = {}

    @classmethod
    def is_throttled(cls, key: str) -> bool:
        """Public form of the throttle, for callers outside this module."""
        return cls._throttled(key)

    @classmethod
    def _throttled(cls, key: str) -> bool:
        """True when this key was reported too recently to report again."""
        from src.api.config import get_settings

        window = get_settings().ERROR_LOG_DEPENDENCY_THROTTLE_SECONDS
        now = time.monotonic()
        last = cls._dependency_last_reported.get(key)
        if last is not None and (now - last) < window:
            return True
        cls._dependency_last_reported[key] = now
        return False

    @classmethod
    async def report_third_party_failure(
        cls,
        *,
        service: str,
        message: str,
        error: Optional[BaseException] = None,
        metadata: Optional[Dict[str, Any]] = None,
        throttle: bool = True,
    ) -> None:
        """
        Record a third-party vendor failure as a ``critical`` row.

        For vendors that are handled gracefully rather than raised -- the email
        provider returns a failed result after exhausting retries, an AI call
        fails inside a LangGraph node -- nothing reaches an exception handler,
        so the outage was invisible. Vendors that *are* raised (WordPress,
        Shopify) already classify as critical through the exception path; this
        is the same severity reached without an exception.

        Throttled and best-effort; never raises.
        """
        try:
            # Throttling suits a vendor that is down and failing every call.
            # It is wrong for a user-initiated action -- someone testing an
            # integration's credentials produces a distinct event each time,
            # and collapsing those would make the second attempt look unlogged.
            if throttle and cls._throttled(f"third-party:{service}"):
                return

            await cls.persist_error_log(
                # No status_code: an unraised vendor failure has no HTTP status,
                # and supplying one would classify it as a 5xx (error) instead.
                api_severity="critical",
                message=message,
                source=f"service {service}",
                path=f"/service/{service}",
                metadata={
                    "service": service,
                    "exception_type": type(error).__name__ if error else None,
                    "error": str(error) if error else None,
                    **(metadata or {}),
                },
            )
        except Exception as report_error:  # noqa: BLE001 - never propagate
            logger.warning(f"Failed to report third-party failure: {report_error}")

    @classmethod
    async def report_dependency_failure(
        cls,
        *,
        dependency: str,
        message: str,
        error: Optional[BaseException] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Record an infrastructure dependency failure (cache, database) as an
        ``error`` row.

        These failures are handled gracefully in the request path -- the cache
        falls back to in-memory, the request still succeeds -- so they raise
        nothing and no exception handler ever sees them. That is correct for
        the caller and wrong for the operator: Redis being down was completely
        invisible on the dashboard.

        Best-effort and never raises; the caller is already on a degraded path.
        """
        from src.api.config import get_settings

        try:
            if cls._throttled(f"dependency:{dependency}"):
                return

            window = get_settings().ERROR_LOG_DEPENDENCY_THROTTLE_SECONDS
            await cls.persist_error_log(
                api_severity=None,
                status_code=503,
                message=message,
                source=f"dependency {dependency}",
                path=f"/dependency/{dependency}",
                metadata={
                    "dependency": dependency,
                    "exception_type": type(error).__name__ if error else None,
                    "error": str(error) if error else None,
                    "throttle_window_seconds": window,
                    **(metadata or {}),
                },
            )
        except Exception as report_error:  # noqa: BLE001 - never propagate
            logger.warning(f"Failed to report dependency failure: {report_error}")

    @classmethod
    async def persist_error_log(
        cls,
        *,
        api_severity: Optional[str] = None,
        message: str,
        source: Optional[str] = None,
        path: Optional[str] = None,
        exception: Any = None,
        status_code: Optional[int] = None,
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
        # ``source`` is a human-readable label ("GET /api/v1/..."), not a path.
        # Passing it to a prefix check that matches on "/api/..." could never
        # match, so this guard silently accepted every excluded path. Callers
        # pass the real path; derive it from the label only as a fallback so an
        # older caller still gets filtering rather than none.
        effective_path = path
        if effective_path is None and source:
            _, _, tail = source.partition(" ")
            effective_path = tail or source

        severity = cls.resolve_error_log_severity(
            exception=exception,
            api_severity=api_severity,
            status_code=status_code,
            path=effective_path or "",
        )
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

        # API calls from Redis metrics
        try:
            from src.api.cache.redis_client import cache as redis_cache
            redis = redis_cache.redis
            api_total = 0
            if redis is not None:
                now_ts = int(time.time())
                period_seconds = int(period_delta.total_seconds())
                minutes = period_seconds // 60

                # Sample up to 1440 minute-buckets (24 hours) for performance
                sample_minutes = min(minutes, 1440)
                pipe = redis.pipeline()
                for i in range(sample_minutes):
                    bucket = (now_ts - (now_ts % 60)) - (i * 60)
                    pipe.get(f"metrics:api:count:{bucket}")
                results = await pipe.execute()
                api_total = sum(int(r or 0) for r in results)

            api_stats = {
                "total": api_total,
                "by_endpoint": [],
                "by_hour": [],
                "note": "Endpoint-level breakdown not yet implemented"
            }
        except Exception:
            api_stats = {
                "total": 0,
                "by_endpoint": [],
                "by_hour": [],
                "note": "API metrics unavailable"
            }

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
