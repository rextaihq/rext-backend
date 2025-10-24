"""
User Security Settings API endpoints.

This module provides security settings and monitoring for the current authenticated user.
Unlike /security/* routes (admin-only), these are user-scoped.
"""

from fastapi import APIRouter, Depends, Request, Query
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from src.api.database.async_database import get_async_db
from src.api.security.dependencies import get_current_user
from src.services.security_service import SecurityService
from src.utils.route_decorators import require_permissions, db_transaction_handler

router = APIRouter()


@router.get("/security/stats", response_model=dict)
@db_transaction_handler("retrieve user security stats", auto_commit=False)
async def get_current_user_security_stats(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
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
    return await service.get_user_security_stats(user_id=user_id)


@router.get("/security/login-history", response_model=dict)
@db_transaction_handler("retrieve user login history", auto_commit=False)
async def get_current_user_login_history(
    request: Request,
    limit: int = Query(50, ge=1, le=100, description="Number of recent logins"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
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

    return await service.get_user_login_history(
        user_id=user_id,
        limit=limit,
        offset=offset
    )


@router.get("/security/active-sessions-count", response_model=dict)
@db_transaction_handler("retrieve active sessions count", auto_commit=False)
async def get_active_sessions_count(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user)
):
    """
    Get count of active sessions for the current user.

    Returns:
    - count: Number of active sessions
    """
    user_id = UUID(current_user.get("identity"))
    service = SecurityService(db)

    return await service.get_active_sessions_count(user_id=user_id)
