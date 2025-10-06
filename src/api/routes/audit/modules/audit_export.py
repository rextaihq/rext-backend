from fastapi import APIRouter, Depends, HTTPException, status, Request, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select
from typing import Optional
from datetime import datetime, timedelta
import csv
import io
import json

from src.api.database.async_database import get_async_db
from src.api.security.dependencies import get_current_user
from src.api.middleware.permissions import is_admin
from src.api.models.audit_models.audit_logs import AuditLog
from src.api.schema.audit_schema import AuditLogExportFormat
from src.utils.response_utils import success
from src.api.middleware.exceptions import WrextValidationException
from src.utils.logger import logger
from src.utils.route_decorators import db_transaction_handler
from .helpers import build_audit_query, format_audit_log


router = APIRouter()


@router.get("/export/download")
@db_transaction_handler("export audit logs", auto_commit=False)
async def export_audit_logs(
    request: Request,
    format: AuditLogExportFormat = Query(AuditLogExportFormat.JSON, description="Export format (json/csv)"),
    user_id: Optional[str] = Query(None, description="Filter by user ID"),
    action: Optional[str] = Query(None, description="Filter by action"),
    resource_type: Optional[str] = Query(None, description="Filter by resource type"),
    date_from: Optional[str] = Query(None, description="Start date (ISO 8601)"),
    date_to: Optional[str] = Query(None, description="End date (ISO 8601)"),
    limit: int = Query(1000, ge=1, le=10000, description="Max records to export"),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
    _: bool = Depends(is_admin)
):
    """
    Export audit logs as JSON or CSV (admin only).

    Query Parameters:
    - format: Export format (json or csv)
    - All filter parameters from list endpoint
    - limit: Maximum records to export (max 10000)

    Returns:
    - File download (JSON or CSV)
    """
    # Build query with filters
    query = await build_audit_query(
        db=db,
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        date_from=date_from,
        date_to=date_to
    )

    # Get logs (limit to prevent memory issues)
    query = query.order_by(AuditLog.created_at.desc()).limit(limit)
    result = await db.execute(query)
    logs = result.scalars().all()

    logger.info(f"Admin {current_user.get('identity')} exporting {len(logs)} audit logs as {format.value}")

    if format == AuditLogExportFormat.JSON:
        # JSON export
        logs_data = [format_audit_log(log, include_details=True) for log in logs]

        json_content = json.dumps({
            "export_date": datetime.utcnow().isoformat(),
            "exported_by": current_user.get("email"),
            "total_records": len(logs_data),
            "logs": logs_data
        }, indent=2)

        return Response(
            content=json_content,
            media_type="application/json",
            headers={
                "Content-Disposition": f"attachment; filename=audit_logs_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
            }
        )

    elif format == AuditLogExportFormat.CSV:
        # CSV export
        output = io.StringIO()
        writer = csv.writer(output)

        # Write header
        writer.writerow([
            "ID", "User ID", "Username", "Email", "Action",
            "Resource Type", "Resource ID", "Workspace ID",
            "IP Address", "Status", "Created At"
        ])

        # Write rows
        for log in logs:
            writer.writerow([
                str(log.id),
                str(log.user_id) if log.user_id else "",
                log.username or "",
                log.user_email or "",
                log.action,
                log.resource_type,
                log.resource_id or "",
                str(log.workspace_id) if log.workspace_id else "",
                str(log.ip_address) if log.ip_address else "",
                log.status,
                log.created_at.isoformat() if log.created_at else ""
            ])

        csv_content = output.getvalue()
        output.close()

        return Response(
            content=csv_content,
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename=audit_logs_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
            }
        )


@router.get("/stats/overview", response_model=dict)
@db_transaction_handler("get audit statistics", auto_commit=False)
async def get_audit_stats(
    request: Request,
    days: int = Query(30, ge=1, le=365, description="Number of days to analyze"),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
    _: bool = Depends(is_admin)
):
    """
    Get audit log statistics (admin only).

    Query Parameters:
    - days: Number of days to analyze (default 30, max 365)

    Returns:
    - Statistics including action counts, top users, recent failures
    """
    cutoff_date = datetime.utcnow() - timedelta(days=days)

    # Total logs
    total_logs_result = await db.execute(
        select(func.count(AuditLog.id)).where(
            AuditLog.created_at >= cutoff_date
        )
    )
    total_logs = total_logs_result.scalar() or 0

    # Logs by action (top 10)
    logs_by_action_result = await db.execute(
        select(
            AuditLog.action,
            func.count(AuditLog.id).label('count')
        ).where(
            AuditLog.created_at >= cutoff_date
        ).group_by(AuditLog.action).order_by(func.count(AuditLog.id).desc()).limit(10)
    )
    logs_by_action = logs_by_action_result.all()

    # Logs by resource type
    logs_by_resource_result = await db.execute(
        select(
            AuditLog.resource_type,
            func.count(AuditLog.id).label('count')
        ).where(
            AuditLog.created_at >= cutoff_date
        ).group_by(AuditLog.resource_type).order_by(func.count(AuditLog.id).desc())
    )
    logs_by_resource = logs_by_resource_result.all()

    # Logs by status
    logs_by_status_result = await db.execute(
        select(
            AuditLog.status,
            func.count(AuditLog.id).label('count')
        ).where(
            AuditLog.created_at >= cutoff_date
        ).group_by(AuditLog.status)
    )
    logs_by_status = logs_by_status_result.all()

    # Most active users (top 10)
    most_active_users_result = await db.execute(
        select(
            AuditLog.user_id,
            AuditLog.username,
            func.count(AuditLog.id).label('action_count')
        ).where(
            AuditLog.created_at >= cutoff_date,
            AuditLog.user_id.isnot(None)
        ).group_by(AuditLog.user_id, AuditLog.username).order_by(
            func.count(AuditLog.id).desc()
        ).limit(10)
    )
    most_active_users = most_active_users_result.all()

    # Recent failures (last 24 hours)
    twenty_four_hours_ago = datetime.utcnow() - timedelta(hours=24)
    recent_failures_result = await db.execute(
        select(func.count(AuditLog.id)).where(
            AuditLog.created_at >= twenty_four_hours_ago,
            AuditLog.status == "failed"
        )
    )
    recent_failures = recent_failures_result.scalar() or 0

    # Format stats
    stats_data = {
        "total_logs": total_logs,
        "period_days": days,
        "logs_by_action": {action: count for action, count in logs_by_action},
        "logs_by_resource": {resource: count for resource, count in logs_by_resource},
        "logs_by_status": {status: count for status, count in logs_by_status},
        "most_active_users": [
            {
                "user_id": str(user_id),
                "username": username,
                "action_count": count
            }
            for user_id, username, count in most_active_users
        ],
        "recent_failures": recent_failures
    }

    return stats_data
