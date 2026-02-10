"""Service providing administrative audit log access."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.models.audit_models.audit_logs import AuditLog
from src.api.schema.audit_schema import AuditLogExportFormat, AuditStatus
from src.api.middleware.exceptions import RextValidationException


class AuditService:
    """Encapsulate filtering and statistics for audit logs."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def fetch_logs(
        self,
        *,
        user_id: Optional[str] = None,
        full_name: Optional[str] = None,
        user_email: Optional[str] = None,
        action: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        workspace_id: Optional[str] = None,
        status_filter: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        limit: int = 1000,
    ) -> Iterable[AuditLog]:
        """Retrieve audit logs using shared query helper."""
        # Lazy import to avoid circular dependency
        from src.api.routes.audit.modules.helpers import build_audit_query

        status_enum = None
        if status_filter:
            try:
                status_enum = AuditStatus(status_filter)
            except ValueError as exc:   
                raise RextValidationException(
                    message=f"Invalid status: {status_filter}",
                    field_errors={"status_filter": ["Unsupported audit status"]},
                ) from exc

        query = await build_audit_query(
            db=self.db,
            user_id=user_id,
            full_name=full_name,
            user_email=user_email,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            workspace_id=workspace_id,
            status_filter=status_enum,
            date_from=date_from,
            date_to=date_to,
        )

        query = query.order_by(AuditLog.created_at.desc()).limit(limit)
        result = await self.db.execute(query)
        return result.scalars().all()

    async def format_export_payload(
        self,
        logs: Iterable[AuditLog],
        *,
        format: AuditLogExportFormat,
        requested_by: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Prepare structured payload for JSON export."""
        # Lazy import to avoid circular dependency
        from src.api.routes.audit.modules.helpers import format_audit_log

        if format is not AuditLogExportFormat.JSON:
            raise ValueError("format must be AuditLogExportFormat.JSON for JSON payloads")

        formatted_logs = [format_audit_log(log, include_details=True) for log in logs]

        return {
            "export_date": datetime.utcnow().isoformat(),
            "exported_by": requested_by,
            "total_records": len(formatted_logs),
            "logs": formatted_logs,
        }

    async def get_statistics(self, days: int) -> Dict[str, Any]:
        """Return summary statistics for audit logs over the provided window."""
        # Lazy import to avoid circular dependency
        from src.api.routes.audit.modules.helpers import format_audit_log

        if days < 1 or days > 365:
            raise RextValidationException(
                message="Analysis period must be between 1 and 365 days",
                field_errors={"days": ["Value out of allowed range"]},
            )

        cutoff = datetime.utcnow() - timedelta(days=days)

        total_logs_result = await self.db.execute(
            select(func.count(AuditLog.id)).where(AuditLog.created_at >= cutoff)
        )
        total_logs = total_logs_result.scalar() or 0

        logs_by_action_result = await self.db.execute(
            select(AuditLog.action, func.count(AuditLog.id))
            .where(AuditLog.created_at >= cutoff)
            .group_by(AuditLog.action)
            .order_by(func.count(AuditLog.id).desc())
            .limit(10)
        )

        logs_by_resource_result = await self.db.execute(
            select(AuditLog.resource_type, func.count(AuditLog.id))
            .where(AuditLog.created_at >= cutoff)
            .group_by(AuditLog.resource_type)
            .order_by(func.count(AuditLog.id).desc())
        )

        logs_by_status_result = await self.db.execute(
            select(AuditLog.status, func.count(AuditLog.id))
            .where(AuditLog.created_at >= cutoff)
            .group_by(AuditLog.status)
        )

        most_active_users_result = await self.db.execute(
            select(AuditLog.user_id, AuditLog.full_name, func.count(AuditLog.id))
            .where(AuditLog.created_at >= cutoff, AuditLog.user_id.isnot(None))
            .group_by(AuditLog.user_id, AuditLog.full_name)
            .order_by(func.count(AuditLog.id).desc())
            .limit(10)
        )

        recent_failures_result = await self.db.execute(
            select(AuditLog)
            .where(AuditLog.created_at >= cutoff, AuditLog.status == "failed")
            .order_by(AuditLog.created_at.desc())
            .limit(25)
        )

        return {
            "total_logs": total_logs,
            "logs_by_action": [
                {"action": action, "count": count} for action, count in logs_by_action_result.all()
            ],
            "logs_by_resource": [
                {"resource_type": resource, "count": count} for resource, count in logs_by_resource_result.all()
            ],
            "logs_by_status": [
                {"status": status, "count": count} for status, count in logs_by_status_result.all()
            ],
            "most_active_users": [
                {
                    "user_id": str(user_id),
                    "full_name": full_name,
                    "action_count": count,
                }
                for user_id, full_name, count in most_active_users_result.all()
            ],
            "recent_failures": [
                format_audit_log(log, include_details=False)
                for log in recent_failures_result.scalars().all()
            ],
            "analysis_period_days": days,
        }
