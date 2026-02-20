from fastapi import APIRouter, Depends, HTTPException, status, Request, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional

from src.api.database.async_database import get_async_db
from src.api.security.dependencies import get_current_user
from src.api.models.audit_models.audit_logs import AuditLog
from src.utils.response_utils import success
from src.api.middleware.exceptions import RextValidationException
from src.utils.logger import logger
from src.utils.route_decorators import db_transaction_handler, require_permissions
from .helpers import build_audit_query, format_audit_log


router = APIRouter()


@router.get("/user/my-logs", response_model=dict)
@require_permissions("audit.read", workspace_scoped=False)
@db_transaction_handler("get user audit logs", "User audit logs retrieved successfully", auto_commit=False)
async def get_my_audit_logs(
    request: Request,
    action: Optional[str] = Query(None, description="Filter by action"),
    resource_type: Optional[str] = Query(None, description="Filter by resource type"),
    date_from: Optional[str] = Query(None, description="Start date (ISO 8601)"),
    date_to: Optional[str] = Query(None, description="End date (ISO 8601)"),
    limit: int = Query(50, ge=1, le=500, description="Results per page"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    db: AsyncSession = Depends(get_async_db),
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
    user_id = current_user.get("identity")

    # Build query with user filter (returns both data query and count query)
    query, count_query = await build_audit_query(
        db=db,
        user_id=user_id,
        action=action,
        resource_type=resource_type,
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

    # Format response (no sensitive details for users)
    logs_data = [format_audit_log(log, include_details=False) for log in logs]

    return {
        "logs": logs_data,
        "total": total_count,
        "limit": limit,
        "offset": offset,
        "has_more": (offset + limit) < total_count
    }
