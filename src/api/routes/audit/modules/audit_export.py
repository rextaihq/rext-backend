
from datetime import datetime, timezone
from io import StringIO
from typing import Optional
from uuid import UUID
import csv
import json

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.database.async_database import get_async_db
from src.api.schema.audit_schema import AuditLogExportFormat
from src.api.schema.response_schemas import SuccessResponse
from src.api.schema.response.audit_responses import AuditStatsOverviewResponse
from src.api.security.dependencies import get_current_user
from src.services.audit_service import AuditService
from src.utils.response_utils import success
from src.utils.route_decorators import db_transaction_handler, require_permissions
from src.utils.audit_helper import create_audit_log

router = APIRouter()


@router.get("/export/download")
# NOTE: Not migrated — returns Response (JSON/CSV file download)
@require_permissions("audit.export", workspace_scoped=False)
@db_transaction_handler("export audit logs", auto_commit=False)
async def export_audit_logs(
    request: Request,
    format: AuditLogExportFormat = Query(AuditLogExportFormat.JSON, description="Export format (json/csv)"),
    user_id: Optional[str] = Query(None, description="Filter by user ID"),
    full_name: Optional[str] = Query(None, description="Filter by user's full name"),
    user_email: Optional[str] = Query(None, description="Filter by user email"),
    action: Optional[str] = Query(None, description="Filter by action"),
    resource_type: Optional[str] = Query(None, description="Filter by resource type"),
    resource_id: Optional[str] = Query(None, description="Filter by resource ID"),
    workspace_id: Optional[str] = Query(None, description="Filter by workspace ID"),
    status_filter: Optional[str] = Query(None, description="Filter by status"),
    date_from: Optional[str] = Query(None, description="Start date (ISO 8601)"),
    date_to: Optional[str] = Query(None, description="End date (ISO 8601)"),
    limit: int = Query(1000, ge=1, le=5000, description="Max records to export"),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """Export audit logs as JSON or CSV (admin only, rate-limited)."""

    # Log the export action itself for audit trail
    admin_user_id = current_user.get("identity")
    await create_audit_log(
        db=db,
        user_id=UUID(admin_user_id) if admin_user_id else None,
        action="audit.export",
        resource_type="audit_log",
        resource_id="bulk_export",
        request=request,
        metadata={
            "format": format.value,
            "limit": limit,
            "filters": {
                "user_id": user_id,
                "action": action,
                "resource_type": resource_type,
                "date_from": date_from,
                "date_to": date_to,
            }
        },
    )

    service = AuditService(db)
    logs = await service.fetch_logs(
        user_id=user_id,
        full_name=full_name,
        user_email=user_email,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        workspace_id=workspace_id,
        status_filter=status_filter,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
    )

    if format == AuditLogExportFormat.JSON:
        payload = await service.format_export_payload(
            logs,
            format=format,
            requested_by=current_user.get("email"),
        )
        content = json.dumps(payload, indent=2)
        return Response(
            content=content,
            media_type="application/json",
            headers={
                "Content-Disposition": f"attachment; filename=audit_logs_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
            },
        )

    # CSV export
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "ID",
            "User ID",
            "Full Name",
            "Email",
            "Action",
            "Resource Type",
            "Resource ID",
            "Workspace ID",
            "IP Address",
            "Status",
            "Created At",
        ]
    )

    for log in logs:
        writer.writerow(
            [
                str(log.id),
                str(log.user_id) if log.user_id else "",
                log.full_name or "",
                log.user_email or "",
                log.action,
                log.resource_type,
                log.resource_id or "",
                str(log.workspace_id) if log.workspace_id else "",
                str(log.ip_address) if log.ip_address else "",
                log.status,
                log.created_at.isoformat() if log.created_at else "",
            ]
        )

    csv_content = output.getvalue()
    output.close()

    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=audit_logs_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"
        },
    )


@router.get("/stats/overview", response_model=SuccessResponse[AuditStatsOverviewResponse])
@require_permissions("audit.read", workspace_scoped=False)
@db_transaction_handler("get audit statistics", auto_commit=False)
async def get_audit_stats(
    request: Request,
    days: int = Query(30, ge=1, le=365, description="Number of days to analyze"),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """Get audit log statistics (admin only)."""
    service = AuditService(db)
    stats = await service.get_statistics(days)

    return success(
        data=stats,
        request=request,
        message="Audit statistics retrieved successfully"
    )
