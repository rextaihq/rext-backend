from fastapi import APIRouter, Depends, HTTPException, status, Request, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional

from src.api.database.async_database import get_async_db
from src.api.security.dependencies import get_current_user
from src.api.models.audit_models.audit_logs import AuditLog
from src.api.schema.audit_schema import AuditStatus
from src.utils.response_utils import success
from src.api.middleware.exceptions import ResourceNotFoundException, RextValidationException
from src.utils.logger import logger
from src.utils.route_decorators import db_transaction_handler, require_permissions
from .helpers import build_audit_query, format_audit_log, resolve_workspace_names
from src.api.schema.response_schemas import SuccessResponse
from src.api.schema.response.audit_responses import (
    AuditLogDetailListResponse,
    AuditLogDetailedResponse,
)


router = APIRouter()


@router.get("/", response_model=SuccessResponse[AuditLogDetailListResponse])
@require_permissions("audit.read", workspace_scoped=False)
@db_transaction_handler("list audit logs", "Audit logs retrieved successfully", auto_commit=False)
async def list_audit_logs(
    request: Request,
    user_id: Optional[str] = Query(None, description="Filter by user ID"),
    full_name: Optional[str] = Query(None, description="Filter by user's full name (partial match)"),
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
    include_details: bool = Query(
        False,
        description=(
            "Include old_values, new_values and metadata on each entry. Off by "
            "default because these payloads are large; the audit UI needs them "
            "to show what actually changed."
        ),
    ),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    List all audit logs with filtering (admin only).

    Query Parameters:
    - user_id: Filter by user UUID
    - full_name: Search by user's full name (partial match)
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
    # Build query with filters (returns both data query and count query)
    query, count_query = await build_audit_query(
        db=db,
        user_id=user_id,
        full_name=full_name,
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
    count_result = await db.execute(count_query)
    total_count = count_result.scalar() or 0

    # Apply ordering and pagination
    query = query.order_by(AuditLog.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(query)
    logs = result.scalars().all()

    # Format response
    workspace_names = await resolve_workspace_names(db, logs)
    logs_data = [
        format_audit_log(
            log,
            include_details=include_details,
            workspace_name=workspace_names.get(log.workspace_id),
        )
        for log in logs
    ]

    return success(
        data={
            "items": logs_data,
            "total": total_count,
            "limit": limit,
            "offset": offset,
            "has_more": (offset + limit) < total_count
        },
        request=request,
        message="Audit logs retrieved successfully"
    )


@router.get("/{audit_log_id}", response_model=SuccessResponse[AuditLogDetailedResponse])
@require_permissions("audit.read", workspace_scoped=False)
@db_transaction_handler("get audit log", "Audit log retrieved successfully", auto_commit=False)
async def get_audit_log(
    request: Request,
    audit_log_id: str,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get detailed audit log entry by ID (admin only).

    Returns full audit log details including old_values, new_values, and metadata.

    Path Parameters:
    - audit_log_id: UUID of the audit log entry

    Returns:
    - Complete audit log entry with change tracking
    """
    # Get audit log
    result = await db.execute(select(AuditLog).where(AuditLog.id == audit_log_id))
    log = result.scalar_one_or_none()

    if not log:
        raise ResourceNotFoundException(
            resource="audit_log",
            identifier=audit_log_id
        )

    # Format with full details
    workspace_names = await resolve_workspace_names(db, [log])
    log_data = format_audit_log(
        log,
        include_details=True,
        workspace_name=workspace_names.get(log.workspace_id),
    )

    return success(
        data=log_data,
        request=request,
        message="Audit log details retrieved successfully"
    )
