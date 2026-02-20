from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional
from datetime import datetime, timezone

from src.api.models.audit_models.audit_logs import AuditLog
from src.api.schema.audit_schema import AuditStatus
from src.api.middleware.exceptions import RextValidationException


async def build_audit_query(
    db: AsyncSession,
    user_id: Optional[str] = None,
    full_name: Optional[str] = None,
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
    query = select(AuditLog)

    # Filter by user
    if user_id:
        query = query.where(AuditLog.user_id == user_id)
    if full_name:
        query = query.where(AuditLog.full_name.ilike(f"%{full_name}%"))
    if user_email:
        query = query.where(AuditLog.user_email.ilike(f"%{user_email}%"))

    # Filter by action (supports prefix matching, e.g., "user." matches all user actions)
    if action:
        if action.endswith("."):
            # Prefix match: "user." matches "user.create", "user.update", etc.
            query = query.where(AuditLog.action.like(f"{action}%"))
        else:
            # Exact match
            query = query.where(AuditLog.action == action)

    # Filter by resource
    if resource_type:
        query = query.where(AuditLog.resource_type == resource_type)
    if resource_id:
        query = query.where(AuditLog.resource_id == resource_id)

    # Filter by workspace
    if workspace_id:
        query = query.where(AuditLog.workspace_id == workspace_id)

    # Filter by status
    if status_filter:
        query = query.where(AuditLog.status == status_filter.value)

    # Filter by date range
    if date_from:
        try:
            date_from_dt = datetime.fromisoformat(date_from.replace("Z", "+00:00"))
            # Ensure timezone-aware: if user provides naive datetime, assume UTC
            if date_from_dt.tzinfo is None:
                date_from_dt = date_from_dt.replace(tzinfo=timezone.utc)
            conditions.append(AuditLog.created_at >= date_from_dt)
        except ValueError:
            raise RextValidationException(
                field="date_from",
                message="Invalid date format. Use ISO 8601 format (e.g., 2025-10-01T00:00:00Z)"
            )

    if date_to:
        try:
            date_to_dt = datetime.fromisoformat(date_to.replace("Z", "+00:00"))
            # Ensure timezone-aware: if user provides naive datetime, assume UTC
            if date_to_dt.tzinfo is None:
                date_to_dt = date_to_dt.replace(tzinfo=timezone.utc)
            conditions.append(AuditLog.created_at <= date_to_dt)
        except ValueError:
            raise RextValidationException(
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
        "full_name": log.full_name,
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
