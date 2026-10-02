"""
User Security Settings API endpoints.

This module provides security settings and monitoring for the current authenticated user.
Unlike /security/* routes (admin-only), these are user-scoped.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.database.async_database import get_async_db
from src.api.schema.response.security_responses import (
    ActiveSessionsCountResponse,
    UserLoginHistoryResponse,
    UserSecurityStatsResponse,
)
from src.api.schema.response_schemas import SuccessResponse
from src.api.security.dependencies import get_current_user
from src.services.security_service import SecurityService
from src.utils.response_utils import success
from src.utils.route_decorators import db_transaction_handler

# No permission gates in this module: every route acts on the caller's own
# security data, so authentication (get_current_user) is sufficient. The former
# user.read gates were redundant — every account held them via the
# platform-floor 'user' role, which has been removed.
router = APIRouter()


@router.get("/security/stats", response_model=SuccessResponse[UserSecurityStatsResponse])
@db_transaction_handler("retrieve user security stats", auto_commit=False)
async def get_current_user_security_stats(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Get security statistics for the current authenticated user.

    Returns:
    - Failed login attempts for this user
    - Account lockout status
    - Last login information
    - Password change history
    - Active sessions count

    This is the user-scoped version of the admin /security/stats endpoint.
    """
    user_id = UUID(current_user.get("identity"))
    service = SecurityService(db)

    # Get user-specific security stats
    service_result = await service.get_user_security_stats(user_id=user_id)
    return success(
        data=service_result["data"],
        request=request,
        message="Security statistics retrieved successfully",
    )


@router.get("/security/login-history", response_model=SuccessResponse[UserLoginHistoryResponse])
@db_transaction_handler("retrieve user login history", auto_commit=False)
async def get_current_user_login_history(
    request: Request,
    limit: int = Query(50, ge=1, le=100, description="Number of recent logins"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Get login history for the current authenticated user.

    Query Parameters:
    - limit: Number of recent login events (max 100)
    - offset: Pagination offset

    Returns:
    - User's login history from audit logs
    - Total count
    - Success/failure status for each login

    This is the user-scoped version of the admin endpoint.
    """
    user_id = UUID(current_user.get("identity"))
    service = SecurityService(db)

    service_result = await service.get_user_login_history(
        user_id=user_id, limit=limit, offset=offset
    )
    return success(
        data=service_result, request=request, message="Login history retrieved successfully"
    )


@router.get(
    "/security/active-sessions-count",
    response_model=SuccessResponse[ActiveSessionsCountResponse],
)
@db_transaction_handler("retrieve active sessions count", auto_commit=False)
async def get_active_sessions_count(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Get count of active sessions for the current user.

    Returns:
    - count: Number of active sessions
    """
    user_id = UUID(current_user.get("identity"))
    service = SecurityService(db)

    service_result = await service.get_active_sessions_count(user_id=user_id)
    return success(
        data=service_result["data"],
        request=request,
        message="Active sessions count retrieved successfully",
    )
