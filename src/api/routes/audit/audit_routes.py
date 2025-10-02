"""
Audit Log API endpoints.

This module provides read-only access to audit logs for administrators and users.
Audit logs are immutable - they can only be created via the internal audit_helper
and queried via these endpoints.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request, Query, Response
from sqlalchemy.orm import Session
from sqlalchemy import func, or_, and_
from typing import List, Optional
from datetime import datetime
import csv
import io
import json

from src.api.database.database import get_db
from src.api.security.auth import get_current_user
from src.api.middleware.permissions import is_admin
from src.api.models.audit_models.audit_logs import AuditLog
from src.api.models.user_models.users import Users
from src.api.schema.audit_schema import (
    AuditLogResponse,
    AuditLogDetailResponse,
    AuditLogListResponse,
    AuditLogFilterParams,
    AuditLogExportFormat,
    AuditLogStatsResponse,
    AuditStatus
)
from src.utils.response_utils import success, error
from src.api.middleware.exceptions import ResourceNotFoundException, WrextValidationException
from src.utils.logger import logger


router = APIRouter(
    prefix="/audit-logs",
    tags=["audit-logs"]
)


def build_audit_query(
    db: Session,
    user_id: Optional[str] = None,
    username: Optional[str] = None,
    user_email: Optional[str] = None,
    action: Optional[str] = None,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    workspace_id: Optional[str] = None,
    status_filter: Optional[AuditStatus] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None
):
    """
    Build audit log query with filters.

    Helper function to construct SQLAlchemy query with optional filters.
    """
    query = db.query(AuditLog)

    # Filter by user
    if user_id:
        query = query.filter(AuditLog.user_id == user_id)
    if username:
        query = query.filter(AuditLog.username.ilike(f"%{username}%"))
    if user_email:
        query = query.filter(AuditLog.user_email.ilike(f"%{user_email}%"))

    # Filter by action (supports prefix matching, e.g., "user." matches all user actions)
    if action:
        if action.endswith("."):
            # Prefix match: "user." matches "user.create", "user.update", etc.
            query = query.filter(AuditLog.action.like(f"{action}%"))
        else:
            # Exact match
            query = query.filter(AuditLog.action == action)

    # Filter by resource
    if resource_type:
        query = query.filter(AuditLog.resource_type == resource_type)
    if resource_id:
        query = query.filter(AuditLog.resource_id == resource_id)

    # Filter by workspace
    if workspace_id:
        query = query.filter(AuditLog.workspace_id == workspace_id)

    # Filter by status
    if status_filter:
        query = query.filter(AuditLog.status == status_filter.value)

    # Filter by date range
    if date_from:
        try:
            date_from_dt = datetime.fromisoformat(date_from.replace("Z", "+00:00"))
            query = query.filter(AuditLog.created_at >= date_from_dt)
        except ValueError:
            raise WrextValidationException(
                field="date_from",
                message="Invalid date format. Use ISO 8601 format (e.g., 2025-10-01T00:00:00Z)"
            )

    if date_to:
        try:
            date_to_dt = datetime.fromisoformat(date_to.replace("Z", "+00:00"))
            query = query.filter(AuditLog.created_at <= date_to_dt)
        except ValueError:
            raise WrextValidationException(
                field="date_to",
                message="Invalid date format. Use ISO 8601 format (e.g., 2025-10-02T23:59:59Z)"
            )

    return query


def format_audit_log(log: AuditLog, include_details: bool = False) -> dict:
    """
    Format audit log for response.

    Args:
        log: AuditLog model instance
        include_details: Whether to include old_values, new_values, metadata

    Returns:
        Dictionary with audit log data
    """
    base_data = {
        "id": str(log.id),
        "user_id": str(log.user_id) if log.user_id else None,
        "username": log.username,
        "user_email": log.user_email,
        "action": log.action,
        "resource_type": log.resource_type,
        "resource_id": log.resource_id,
        "workspace_id": str(log.workspace_id) if log.workspace_id else None,
        "ip_address": str(log.ip_address) if log.ip_address else None,
        "user_agent": log.user_agent,
        "request_id": log.request_id,
        "status": log.status,
        "created_at": log.created_at.isoformat() if log.created_at else None
    }

    if include_details:
        base_data.update({
            "old_values": log.old_values,
            "new_values": log.new_values,
            "metadata": log.audit_metadata,
            "error_message": log.error_message
        })

    return base_data


@router.get("", response_model=dict)
def list_audit_logs(
    request: Request,
    user_id: Optional[str] = Query(None, description="Filter by user ID"),
    username: Optional[str] = Query(None, description="Filter by username (partial match)"),
    user_email: Optional[str] = Query(None, description="Filter by user email (partial match)"),
    action: Optional[str] = Query(None, description="Filter by action (exact or prefix with '.')"),
    resource_type: Optional[str] = Query(None, description="Filter by resource type"),
    resource_id: Optional[str] = Query(None, description="Filter by resource ID"),
    workspace_id: Optional[str] = Query(None, description="Filter by workspace ID"),
    status_filter: Optional[AuditStatus] = Query(None, description="Filter by status"),
    date_from: Optional[str] = Query(None, description="Start date (ISO 8601)"),
    date_to: Optional[str] = Query(None, description="End date (ISO 8601)"),
    limit: int = Query(50, ge=1, le=1000, description="Results per page"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    _: bool = Depends(is_admin)
):
    """
    List all audit logs with filtering (admin only).

    Query Parameters:
    - user_id: Filter by user UUID
    - username: Search by username (partial match)
    - user_email: Search by email (partial match)
    - action: Filter by action (exact match or prefix with '.', e.g., 'user.' for all user actions)
    - resource_type: Filter by resource type
    - resource_id: Filter by specific resource ID
    - workspace_id: Filter by workspace UUID
    - status: Filter by status (success/failed/partial)
    - date_from: Start date (ISO 8601 format)
    - date_to: End date (ISO 8601 format)
    - limit: Results per page (max 1000)
    - offset: Pagination offset

    Returns:
    - Paginated list of audit logs
    """
    try:
        # Build query with filters
        query = build_audit_query(
            db=db,
            user_id=user_id,
            username=username,
            user_email=user_email,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            workspace_id=workspace_id,
            status_filter=status_filter,
            date_from=date_from,
            date_to=date_to
        )

        # Get total count
        total_count = query.count()

        # Apply ordering and pagination
        logs = query.order_by(AuditLog.created_at.desc()).offset(offset).limit(limit).all()

        # Format response
        logs_data = [format_audit_log(log, include_details=False) for log in logs]

        return success(
            data={
                "logs": logs_data,
                "total": total_count,
                "limit": limit,
                "offset": offset,
                "has_more": (offset + limit) < total_count
            },
            request=request,
            message=f"Retrieved {len(logs_data)} audit log(s)"
        )

    except (WrextValidationException, HTTPException):
        raise
    except Exception as e:
        logger.error(f"Error listing audit logs: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve audit logs"
        )


@router.get("/{audit_log_id}", response_model=dict)
def get_audit_log(
    request: Request,
    audit_log_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    _: bool = Depends(is_admin)
):
    """
    Get detailed audit log entry by ID (admin only).

    Returns full audit log details including old_values, new_values, and metadata.

    Path Parameters:
    - audit_log_id: UUID of the audit log entry

    Returns:
    - Complete audit log entry with change tracking
    """
    try:
        # Get audit log
        log = db.query(AuditLog).filter(AuditLog.id == audit_log_id).first()

        if not log:
            raise ResourceNotFoundException(
                resource="audit_log",
                identifier=audit_log_id
            )

        # Format with full details
        log_data = format_audit_log(log, include_details=True)

        return success(
            data=log_data,
            request=request,
            message="Audit log retrieved successfully"
        )

    except (ResourceNotFoundException, HTTPException):
        raise
    except Exception as e:
        logger.error(f"Error retrieving audit log {audit_log_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve audit log"
        )


@router.get("/user/my-logs", response_model=dict)
def get_my_audit_logs(
    request: Request,
    action: Optional[str] = Query(None, description="Filter by action"),
    resource_type: Optional[str] = Query(None, description="Filter by resource type"),
    date_from: Optional[str] = Query(None, description="Start date (ISO 8601)"),
    date_to: Optional[str] = Query(None, description="End date (ISO 8601)"),
    limit: int = Query(50, ge=1, le=500, description="Results per page"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get current user's audit logs (self-service).

    Users can only see audit logs for actions they performed.

    Query Parameters:
    - action: Filter by action type
    - resource_type: Filter by resource type
    - date_from: Start date (ISO 8601)
    - date_to: End date (ISO 8601)
    - limit: Results per page (max 500)
    - offset: Pagination offset

    Returns:
    - Paginated list of user's audit logs
    """
    try:
        user_id = current_user.get("identity")

        # Build query with user filter
        query = build_audit_query(
            db=db,
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            date_from=date_from,
            date_to=date_to
        )

        # Get total count
        total_count = query.count()

        # Apply ordering and pagination
        logs = query.order_by(AuditLog.created_at.desc()).offset(offset).limit(limit).all()

        # Format response (no sensitive details for users)
        logs_data = [format_audit_log(log, include_details=False) for log in logs]

        return success(
            data={
                "logs": logs_data,
                "total": total_count,
                "limit": limit,
                "offset": offset,
                "has_more": (offset + limit) < total_count
            },
            request=request,
            message=f"Retrieved {len(logs_data)} audit log(s)"
        )

    except (WrextValidationException, HTTPException):
        raise
    except Exception as e:
        logger.error(f"Error retrieving user audit logs: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve audit logs"
        )


@router.get("/export/download")
def export_audit_logs(
    request: Request,
    format: AuditLogExportFormat = Query(AuditLogExportFormat.JSON, description="Export format (json/csv)"),
    user_id: Optional[str] = Query(None, description="Filter by user ID"),
    action: Optional[str] = Query(None, description="Filter by action"),
    resource_type: Optional[str] = Query(None, description="Filter by resource type"),
    date_from: Optional[str] = Query(None, description="Start date (ISO 8601)"),
    date_to: Optional[str] = Query(None, description="End date (ISO 8601)"),
    limit: int = Query(1000, ge=1, le=10000, description="Max records to export"),
    db: Session = Depends(get_db),
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
    try:
        # Build query with filters
        query = build_audit_query(
            db=db,
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            date_from=date_from,
            date_to=date_to
        )

        # Get logs (limit to prevent memory issues)
        logs = query.order_by(AuditLog.created_at.desc()).limit(limit).all()

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

    except (WrextValidationException, HTTPException):
        raise
    except Exception as e:
        logger.error(f"Error exporting audit logs: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to export audit logs"
        )


@router.get("/stats/overview", response_model=dict)
def get_audit_stats(
    request: Request,
    days: int = Query(30, ge=1, le=365, description="Number of days to analyze"),
    db: Session = Depends(get_db),
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
    try:
        from datetime import timedelta

        cutoff_date = datetime.utcnow() - timedelta(days=days)

        # Total logs
        total_logs = db.query(func.count(AuditLog.id)).filter(
            AuditLog.created_at >= cutoff_date
        ).scalar() or 0

        # Logs by action (top 10)
        logs_by_action = db.query(
            AuditLog.action,
            func.count(AuditLog.id).label('count')
        ).filter(
            AuditLog.created_at >= cutoff_date
        ).group_by(AuditLog.action).order_by(func.count(AuditLog.id).desc()).limit(10).all()

        # Logs by resource type
        logs_by_resource = db.query(
            AuditLog.resource_type,
            func.count(AuditLog.id).label('count')
        ).filter(
            AuditLog.created_at >= cutoff_date
        ).group_by(AuditLog.resource_type).order_by(func.count(AuditLog.id).desc()).all()

        # Logs by status
        logs_by_status = db.query(
            AuditLog.status,
            func.count(AuditLog.id).label('count')
        ).filter(
            AuditLog.created_at >= cutoff_date
        ).group_by(AuditLog.status).all()

        # Most active users (top 10)
        most_active_users = db.query(
            AuditLog.user_id,
            AuditLog.username,
            func.count(AuditLog.id).label('action_count')
        ).filter(
            AuditLog.created_at >= cutoff_date,
            AuditLog.user_id.isnot(None)
        ).group_by(AuditLog.user_id, AuditLog.username).order_by(
            func.count(AuditLog.id).desc()
        ).limit(10).all()

        # Recent failures (last 24 hours)
        twenty_four_hours_ago = datetime.utcnow() - timedelta(hours=24)
        recent_failures = db.query(func.count(AuditLog.id)).filter(
            AuditLog.created_at >= twenty_four_hours_ago,
            AuditLog.status == "failed"
        ).scalar() or 0

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

        return success(
            data=stats_data,
            request=request,
            message=f"Audit statistics for last {days} days retrieved successfully"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving audit statistics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve audit statistics"
        )
