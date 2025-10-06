"""
Security Monitoring API endpoints.

This module provides security monitoring and management operations for administrators.
Includes failed login tracking, locked account management, and security statistics.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_
from typing import List, Optional
from datetime import datetime, timedelta
import uuid

from src.api.database.async_database import get_async_db
from src.api.security.dependencies import get_current_user
from src.api.middleware.permissions import is_admin
from src.api.models.user_models.users import Users
from src.api.models.audit_models.audit_logs import AuditLog
from src.api.schema.security_schema import (
    FailedLoginResponse,
    LockedAccountResponse,
    SecurityStatsResponse,
    LoginHistoryResponse,
    SuspiciousActivityResponse,
    UnlockAccountRequest,
    ResetFailedAttemptsRequest
)
from src.utils.response_utils import success, error
from src.utils.db_utils import get_or_404
from src.api.middleware.exceptions import ResourceNotFoundException, BusinessRuleViolationException
from src.utils.logger import logger
from src.utils.audit_helper import create_audit_log
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
    # Get users with failed login attempts
    query = select(Users).where(
        Users.failed_login_attempts > 0
    ).order_by(Users.failed_login_attempts.desc())

    total_count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total_count = total_count_result.scalar() or 0

    users_result = await db.execute(query.offset(offset).limit(limit))
    users = users_result.scalars().all()

    users_data = []
    for user in users:
        is_locked = bool(user.locked_until and user.locked_until > datetime.utcnow())

        users_data.append({
            "id": str(user.id),
            "email": user.email,
            "username": user.username,
            "failed_attempts": user.failed_login_attempts,
            "locked_until": user.locked_until.isoformat() if user.locked_until else None,
            "last_failed_at": user.updated_at.isoformat() if user.updated_at else None,
            "is_locked": is_locked
        })

    return {
        "users": users_data,
        "total": total_count,
        "limit": limit,
        "offset": offset,
        "has_more": (offset + limit) < total_count
    }


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
    # Build query
    query = select(Users).where(Users.locked_until.isnot(None))

    if not include_expired:
        query = query.where(Users.locked_until > datetime.utcnow())

    query = query.order_by(Users.locked_until.desc())

    total_count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total_count = total_count_result.scalar() or 0

    users_result = await db.execute(query.offset(offset).limit(limit))
    users = users_result.scalars().all()

    locked_accounts = []
    now = datetime.utcnow()

    for user in users:
        if user.locked_until:
            remaining_minutes = max(0, int((user.locked_until - now).total_seconds() / 60))

            locked_accounts.append({
                "id": str(user.id),
                "email": user.email,
                "username": user.username,
                "locked_until": user.locked_until.isoformat(),
                "failed_attempts": user.failed_login_attempts,
                "remaining_lock_time_minutes": remaining_minutes
            })

    return {
        "locked_accounts": locked_accounts,
        "total": total_count,
        "limit": limit,
        "offset": offset,
        "has_more": (offset + limit) < total_count
    }


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
    admin_user_id = current_user.get("identity")

    # Get user
    user = await get_or_404(db, Users, user_id, "user")

    # Check if account is locked
    if not user.locked_until or user.locked_until <= datetime.utcnow():
        raise BusinessRuleViolationException(
            message="Account is not currently locked",
            rule="account_unlock_validation"
        )

    # Unlock account
    user.locked_until = None
    user.failed_login_attempts = 0
    user.updated_at = datetime.utcnow()

    await db.flush()
    await db.refresh(user)

    # Create audit log
    admin_user_result = await db.execute(select(Users).where(Users.id == admin_user_id))
    admin_user = admin_user_result.scalar_one_or_none()

    create_audit_log(
        db=db,
        user_id=admin_user_id,
        action="security.unlock_account",
        resource_type="user",
        resource_id=str(user_id),
        request=request,
        username=admin_user.username if admin_user else None,
        user_email=admin_user.email if admin_user else None,
        old_values={"locked": True},
        new_values={"locked": False},
        metadata={"reason": unlock_data.reason}
    )

    logger.info(f"Admin {admin_user_id} unlocked account {user_id}. Reason: {unlock_data.reason}")

    return {
        "user_id": str(user.id),
        "email": user.email,
        "username": user.username,
        "locked": False,
        "failed_attempts": 0
    }


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
    admin_user_id = current_user.get("identity")

    # Get user
    user = await get_or_404(db, Users, user_id, "user")

    old_attempts = user.failed_login_attempts

    # Reset counter
    user.failed_login_attempts = 0
    user.updated_at = datetime.utcnow()

    await db.flush()
    await db.refresh(user)

    # Create audit log
    admin_user_result = await db.execute(select(Users).where(Users.id == admin_user_id))
    admin_user = admin_user_result.scalar_one_or_none()

    create_audit_log(
        db=db,
        user_id=admin_user_id,
        action="security.reset_failed_attempts",
        resource_type="user",
        resource_id=str(user_id),
        request=request,
        username=admin_user.username if admin_user else None,
        user_email=admin_user.email if admin_user else None,
        old_values={"failed_attempts": old_attempts},
        new_values={"failed_attempts": 0},
        metadata={"reason": reset_data.reason}
    )

    logger.info(f"Admin {admin_user_id} reset failed attempts for {user_id}. Reason: {reset_data.reason}")

    return {
        "user_id": str(user.id),
        "email": user.email,
        "username": user.username,
        "failed_attempts": 0,
        "previous_attempts": old_attempts
    }


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
    now = datetime.utcnow()
    last_24h = now - timedelta(hours=24)
    last_7d = now - timedelta(days=7)
    last_30d = now - timedelta(days=30)

    # Failed login stats from audit logs
    failed_24h_result = await db.execute(
        select(func.count(AuditLog.id)).where(
            AuditLog.action == "auth.login",
            AuditLog.status == "failed",
            AuditLog.created_at >= last_24h
        )
    )
    failed_logins_24h = failed_24h_result.scalar() or 0

    failed_7d_result = await db.execute(
        select(func.count(AuditLog.id)).where(
            AuditLog.action == "auth.login",
            AuditLog.status == "failed",
            AuditLog.created_at >= last_7d
        )
    )
    failed_logins_7d = failed_7d_result.scalar() or 0

    failed_30d_result = await db.execute(
        select(func.count(AuditLog.id)).where(
            AuditLog.action == "auth.login",
            AuditLog.status == "failed",
            AuditLog.created_at >= last_30d
        )
    )
    failed_logins_30d = failed_30d_result.scalar() or 0

    # Locked accounts
    locked_result = await db.execute(
        select(func.count(Users.id)).where(
            Users.locked_until.isnot(None),
            Users.locked_until > now
        )
    )
    currently_locked = locked_result.scalar() or 0

    locked_24h_result = await db.execute(
        select(func.count(AuditLog.id)).where(
            AuditLog.action == "user.lock",
            AuditLog.created_at >= last_24h
        )
    )
    locked_24h = locked_24h_result.scalar() or 0

    # Password security
    pwd_reset_result = await db.execute(
        select(func.count(AuditLog.id)).where(
            AuditLog.action == "auth.password_reset",
            AuditLog.created_at >= last_24h
        )
    )
    password_resets_24h = pwd_reset_result.scalar() or 0

    pwd_change_result = await db.execute(
        select(func.count(AuditLog.id)).where(
            AuditLog.action == "auth.password_change",
            AuditLog.created_at >= last_24h
        )
    )
    password_changes_24h = pwd_change_result.scalar() or 0

    # Account activity
    new_users_result = await db.execute(
        select(func.count(Users.id)).where(Users.created_at >= last_24h)
    )
    new_registrations_24h = new_users_result.scalar() or 0

    verify_result = await db.execute(
        select(func.count(AuditLog.id)).where(
            AuditLog.action == "user.verify_email",
            AuditLog.created_at >= last_24h
        )
    )
    email_verifications_24h = verify_result.scalar() or 0

    # Top failed login IPs (from audit logs)
    top_ips_result = await db.execute(
        select(
            AuditLog.ip_address,
            func.count(AuditLog.id).label('count')
        ).where(
            AuditLog.action == "auth.login",
            AuditLog.status == "failed",
            AuditLog.created_at >= last_7d,
            AuditLog.ip_address.isnot(None)
        ).group_by(AuditLog.ip_address).order_by(
            func.count(AuditLog.id).desc()
        ).limit(10)
    )
    top_ips = top_ips_result.all()

    top_failed_login_ips = [
        {"ip": str(ip), "count": count}
        for ip, count in top_ips
    ]

    # Top users with failed logins
    top_users_result = await db.execute(
        select(
            Users.email,
            Users.failed_login_attempts.label('count')
        ).where(
            Users.failed_login_attempts > 0
        ).order_by(Users.failed_login_attempts.desc()).limit(10)
    )
    top_users_query = top_users_result.all()

    top_failed_login_users = [
        {"email": email, "count": count}
        for email, count in top_users_query
    ]

    return {
        "failed_logins_last_24h": failed_logins_24h,
        "failed_logins_last_7d": failed_logins_7d,
        "failed_logins_last_30d": failed_logins_30d,
        "currently_locked_accounts": currently_locked,
        "locked_accounts_last_24h": locked_24h,
        "password_resets_last_24h": password_resets_24h,
        "password_changes_last_24h": password_changes_24h,
        "new_registrations_last_24h": new_registrations_24h,
        "email_verifications_last_24h": email_verifications_24h,
        "top_failed_login_ips": top_failed_login_ips,
        "top_failed_login_users": top_failed_login_users
    }


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
    # Get user
    user = await get_or_404(db, Users, user_id, "user")

    # Get login events from audit log
    events_result = await db.execute(
        select(AuditLog).where(
            AuditLog.user_id == user_id,
            AuditLog.action.like("auth.login%")
        ).order_by(AuditLog.created_at.desc()).limit(limit)
    )
    login_events = events_result.scalars().all()

    login_history = []
    for event in login_events:
        login_history.append({
            "timestamp": event.created_at.isoformat() if event.created_at else None,
            "ip_address": str(event.ip_address) if event.ip_address else None,
            "user_agent": event.user_agent,
            "status": event.status,
            "action": event.action
        })

    return {
        "user_id": str(user.id),
        "username": user.username,
        "email": user.email,
        "total_logins": user.login_count,
        "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
        "failed_login_attempts": user.failed_login_attempts,
        "login_history": login_history
    }
