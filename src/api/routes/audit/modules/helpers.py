from datetime import datetime
from typing import Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.middleware.exceptions import RextValidationException
from src.api.models.audit_models.audit_logs import AuditLog
from src.api.schema.audit_schema import AuditStatus


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
    date_to: Optional[str] = None,
) -> Tuple[select, select]:
    """
    Build audit log data query and count query with shared filters.

    Returns a tuple of (data_query, count_query) where both queries share
    the same WHERE conditions. This avoids the need to extract where clauses
    from one query to apply to another.

    Args:
        db: Async database session
        user_id: Filter by user UUID
        full_name: Filter by full name (partial match)
        user_email: Filter by email (partial match)
        action: Filter by action (exact match or prefix with '.')
        resource_type: Filter by resource type
        resource_id: Filter by resource ID
        workspace_id: Filter by workspace UUID
        status_filter: Filter by AuditStatus enum
        date_from: Start date (ISO 8601)
        date_to: End date (ISO 8601)

    Returns:
        Tuple of (data_query, count_query) with same filter conditions applied
    """
    conditions = []

    # Filter by user
    if user_id:
        conditions.append(AuditLog.user_id == user_id)
    if full_name:
        conditions.append(AuditLog.full_name.ilike(f"%{full_name}%"))
    if user_email:
        conditions.append(AuditLog.user_email.ilike(f"%{user_email}%"))

    # Filter by action (supports prefix matching, e.g., "user." matches all user actions)
    if action:
        if action.endswith("."):
            conditions.append(AuditLog.action.like(f"{action}%"))
        else:
            conditions.append(AuditLog.action == action)

    # Filter by resource
    if resource_type:
        conditions.append(AuditLog.resource_type == resource_type)
    if resource_id:
        conditions.append(AuditLog.resource_id == resource_id)

    # Filter by workspace
    if workspace_id:
        conditions.append(AuditLog.workspace_id == workspace_id)

    # Filter by status
    if status_filter:
        conditions.append(AuditLog.status == status_filter.value)

    # Filter by date range
    if date_from:
        try:
            date_from_dt = datetime.fromisoformat(date_from.replace("Z", "+00:00"))
            conditions.append(AuditLog.created_at >= date_from_dt)
        except ValueError:
            raise RextValidationException(
                field="date_from",
                message="Invalid date format. Use ISO 8601 format (e.g., 2025-10-01T00:00:00Z)",
            )

    if date_to:
        try:
            date_to_dt = datetime.fromisoformat(date_to.replace("Z", "+00:00"))
            conditions.append(AuditLog.created_at <= date_to_dt)
        except ValueError:
            raise RextValidationException(
                field="date_to",
                message="Invalid date format. Use ISO 8601 format (e.g., 2025-10-02T23:59:59Z)",
            )

    # Build both queries from the same conditions list
    data_query = select(AuditLog)
    count_query = select(func.count()).select_from(AuditLog)

    if conditions:
        data_query = data_query.where(*conditions)
        count_query = count_query.where(*conditions)

    return data_query, count_query


async def resolve_workspace_names(db, logs) -> dict:
    """Map workspace_id -> name for a page of audit logs.

    The audit row only stores the workspace FK, so the name is resolved on
    read. One batched query per page; soft-deleted workspaces are included on
    purpose, since audit entries for a deleted workspace still need a label.
    """
    from src.api.models.workspace_models.workspace_model import WorkspaceModel

    ids = {log.workspace_id for log in logs if log.workspace_id}
    if not ids:
        return {}
    result = await db.execute(
        select(WorkspaceModel.id, WorkspaceModel.name).where(WorkspaceModel.id.in_(ids))
    )
    return {row.id: row.name for row in result}


def format_audit_log(
    log: AuditLog, include_details: bool = False, workspace_name: str = None
) -> dict:
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
        "workspace_name": workspace_name,
        "ip_address": str(log.ip_address) if log.ip_address else None,
        "user_agent": log.user_agent,
        "request_id": log.request_id,
        "status": log.status,
        "created_at": log.created_at.isoformat() if log.created_at else None,
    }

    if include_details:
        base_data.update(
            {
                "old_values": log.old_values,
                "new_values": log.new_values,
                "metadata": log.audit_metadata,
                "error_message": log.error_message,
            }
        )

    return base_data
