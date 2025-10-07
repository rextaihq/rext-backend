"""
Security Monitoring API endpoints.

This module provides security monitoring and management operations for administrators.
Includes failed login tracking, locked account management, and security statistics.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from uuid import UUID

from src.api.database.async_database import get_async_db
from src.api.security.dependencies import get_current_user
from src.api.middleware.permissions import is_admin
from src.api.schema.security_schema import (
    FailedLoginResponse,
    LockedAccountResponse,
    SecurityStatsResponse,
    LoginHistoryResponse,
    SuspiciousActivityResponse,
    UnlockAccountRequest,
    ResetFailedAttemptsRequest
)
from src.services.security_service import SecurityService
from src.utils.route_decorators import db_transaction_handler, require_permissions


router = APIRouter(
    prefix="/security",
    tags=["security-monitoring"]
)


@router.get("/failed-logins", response_model=dict)
@db_transaction_handler("retrieve failed logins", auto_commit=False)
async def get_failed_logins(
    request: Request,
    limit: int = Query(50, ge=1, le=500, description="Results per page"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
    _: bool = Depends(is_admin)
):
    """
    Get users with failed login attempts (admin only).

    Query Parameters:
    - limit: Results per page (max 500)
    - offset: Pagination offset

    Returns:
    - List of users with failed login attempts
    """
    service = SecurityService(db)
    return await service.get_failed_logins(limit=limit, offset=offset)


@router.get("/locked-accounts", response_model=dict)
@db_transaction_handler("retrieve locked accounts", auto_commit=False)
async def get_locked_accounts(
    request: Request,
    include_expired: bool = Query(False, description="Include accounts with expired locks"),
    limit: int = Query(50, ge=1, le=500, description="Results per page"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
    _: bool = Depends(is_admin)
):
    """
    Get locked user accounts (admin only).

    Query Parameters:
    - include_expired: Include accounts with expired locks (default: false)
    - limit: Results per page (max 500)
    - offset: Pagination offset

    Returns:
    - List of locked accounts
    """
    service = SecurityService(db)
    return await service.get_locked_accounts(
        include_expired=include_expired,
        limit=limit,
        offset=offset
    )


@router.post("/{user_id}/unlock", response_model=dict)
@db_transaction_handler("unlock account", auto_commit=True)
@require_permissions("user.update", workspace_scoped=False)
async def unlock_account(
    request: Request,
    user_id: str,
    unlock_data: UnlockAccountRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
    _: bool = Depends(is_admin)
):
    """
    Manually unlock a user account (admin only).

    Path Parameters:
    - user_id: UUID of the user to unlock

    Body:
    - reason: Optional reason for unlocking

    Returns:
    - Updated user account status
    """
    admin_user_id = UUID(current_user.get("identity"))
    service = SecurityService(db)

    return await service.unlock_account(
        user_id=UUID(user_id),
        admin_user_id=admin_user_id,
        reason=unlock_data.reason,
        request=request
    )


@router.post("/{user_id}/reset-failed-attempts", response_model=dict)
@db_transaction_handler("reset failed login attempts", auto_commit=True)
@require_permissions("user.update", workspace_scoped=False)
async def reset_failed_attempts(
    request: Request,
    user_id: str,
    reset_data: ResetFailedAttemptsRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
    _: bool = Depends(is_admin)
):
    """
    Reset failed login attempts counter (admin only).

    Path Parameters:
    - user_id: UUID of the user

    Body:
    - reason: Optional reason for reset

    Returns:
    - Updated user account status
    """
    admin_user_id = UUID(current_user.get("identity"))
    service = SecurityService(db)

    return await service.reset_failed_attempts(
        user_id=UUID(user_id),
        admin_user_id=admin_user_id,
        reason=reset_data.reason,
        request=request
    )


@router.get("/stats", response_model=dict)
@db_transaction_handler("retrieve security statistics", auto_commit=False)
async def get_security_stats(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
    _: bool = Depends(is_admin)
):
    """
    Get security statistics dashboard (admin only).

    Returns:
    - Comprehensive security statistics including:
      - Failed login trends
      - Locked accounts
      - Password security metrics
      - Account activity
      - Top offenders by IP and user
    """
    service = SecurityService(db)
    return await service.get_security_stats()


@router.get("/login-history/{user_id}", response_model=dict)
@db_transaction_handler("retrieve login history", auto_commit=False)
async def get_user_login_history(
    request: Request,
    user_id: str,
    limit: int = Query(50, ge=1, le=100, description="Number of recent logins"),
    db: AsyncSession = Depends(get_async_db),
    current_user: dict = Depends(get_current_user),
    _: bool = Depends(is_admin)
):
    """
    Get login history for a specific user (admin only).

    Path Parameters:
    - user_id: UUID of the user

    Query Parameters:
    - limit: Number of recent login events (max 100)

    Returns:
    - User's login history from audit logs
    """
    service = SecurityService(db)
    return await service.get_user_login_history(user_id=UUID(user_id), limit=limit)
