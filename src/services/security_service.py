"""
Security Service - Business Logic for Security Monitoring and Management

This service encapsulates all business logic related to security monitoring,
including failed login tracking, account locking, and security statistics.

Responsibilities:
- Failed login tracking and analysis
- Locked account management
- Security statistics and dashboards
- Login history retrieval
- Account unlock operations
- Failed attempts reset

Does NOT:
- Handle HTTP requests/responses (that's routes)
- Commit transactions (that's decorators/routes)
- Check authentication (that's decorators)
"""

from typing import List, Dict, Any, Optional
from uuid import UUID
from datetime import datetime, timedelta,timezone

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_

from src.api.models.user_models.users import Users
from src.api.models.audit_models.audit_logs import AuditLog
from src.utils.logger import logger
from src.api.middleware.exceptions import (
    ResourceNotFoundException,
    RextValidationException
)


class SecurityService:
    """Service for security monitoring and management"""

    def __init__(self, db: AsyncSession):
        """
        Initialize SecurityService.

        Args:
            db: Async database session
        """
        self.db = db

    async def get_failed_logins(
        self,
        limit: int = 50,
        offset: int = 0
    ) -> Dict[str, Any]:
        """
        Get users with failed login attempts.

        Business Rules:
        - Only includes users with failed_login_attempts > 0
        - Orders by failed attempts (descending)
        - Calculates lock status dynamically

        Args:
            limit: Results per page (1-500)
            offset: Pagination offset

        Returns:
            Dict with:
            {
                "users": [...],
                "total": count,
                "limit": limit,
                "offset": offset,
                "has_more": bool
            }
        """
        # Query users with failed attempts
        query = select(Users).where(
            Users.failed_login_attempts > 0
        ).order_by(Users.failed_login_attempts.desc())

        # Get total count
        total_count_result = await self.db.execute(
            select(func.count()).select_from(query.subquery())
        )
        total_count = total_count_result.scalar() or 0

        # Get paginated users
        users_result = await self.db.execute(query.offset(offset).limit(limit))
        users = users_result.scalars().all()

        # Format response
        users_data = []
        now = datetime.now(timezone.utc)

        for user in users:
            is_locked = bool(user.locked_until and user.locked_until > now)

            users_data.append({
                "id": str(user.id),
                "email": user.email,
                "full_name": user.full_name,
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

    async def get_locked_accounts(
        self,
        include_expired: bool = False,
        limit: int = 50,
        offset: int = 0
    ) -> Dict[str, Any]:
        """
        Get locked user accounts.

        Args:
            include_expired: Include accounts with expired locks
            limit: Results per page (1-500)
            offset: Pagination offset

        Returns:
            Dict with locked accounts list and pagination info
        """
        # Build query
        query = select(Users).where(Users.locked_until.isnot(None))

        if not include_expired:
            query = query.where(Users.locked_until > datetime.now(timezone.utc))

        query = query.order_by(Users.locked_until.desc())

        # Get total count
        total_count_result = await self.db.execute(
            select(func.count()).select_from(query.subquery())
        )
        total_count = total_count_result.scalar() or 0

        # Get paginated users
        users_result = await self.db.execute(query.offset(offset).limit(limit))
        users = users_result.scalars().all()

        # Format response
        locked_accounts = []
        now = datetime.now(timezone.utc)

        for user in users:
            if user.locked_until:
                remaining_minutes = max(0, int((user.locked_until - now).total_seconds() / 60))

                locked_accounts.append({
                    "id": str(user.id),
                    "email": user.email,
                    "full_name": user.full_name,
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

    async def unlock_account(self, user_id: UUID) -> Users:
        """
        Manually unlock a user account.

        Business Rules:
        - Account must be currently locked
        - Resets locked_until to None
        - Resets failed_login_attempts to 0

        Args:
            user_id: User UUID

        Returns:
            Updated Users object

        Raises:
            ResourceNotFoundException: If user not found
            RextValidationException: If account not locked
        """
        # Get user
        user = await self._get_user_or_404(user_id)

        # Check if account is actually locked
        if not user.locked_until or user.locked_until <= datetime.now(timezone.utc):
            raise RextValidationException(
                message="Account is not currently locked",
                field_errors={"user_id": ["Account not locked"]}
            )

        # Unlock account
        user.locked_until = None
        user.failed_login_attempts = 0
        user.updated_at = datetime.now(timezone.utc)

        await self.db.flush()
        await self.db.refresh(user)

        logger.info(
            f"Account unlocked: {user.email}",
            extra={"user_id": str(user_id)}
        )

        return user

    async def reset_failed_attempts(self, user_id: UUID) -> Dict[str, Any]:
        """
        Reset failed login attempts counter for a user.

        Args:
            user_id: User UUID

        Returns:
            Dict with old and new attempt counts

        Raises:
            ResourceNotFoundException: If user not found
        """
        # Get user
        user = await self._get_user_or_404(user_id)

        old_attempts = user.failed_login_attempts

        # Reset counter
        user.failed_login_attempts = 0
        user.updated_at = datetime.now(timezone.utc)

        await self.db.flush()
        await self.db.refresh(user)

        logger.info(
            f"Failed attempts reset for {user.email}: {old_attempts} -> 0",
            extra={"user_id": str(user_id)}
        )

        return {
            "user_id": str(user.id),
            "email": user.email,
            "full_name": user.full_name,
            "failed_attempts": 0,
            "previous_attempts": old_attempts
        }

    async def get_security_stats(self) -> Dict[str, Any]:
        """
        Get comprehensive security statistics.

        Returns:
            Dict with:
            - Failed login trends (24h, 7d, 30d)
            - Locked accounts (current, 24h)
            - Password security metrics
            - Account activity (registrations, verifications)
            - Top offenders by IP and user
        """
        now = datetime.now(timezone.utc)
        last_24h = now - timedelta(hours=24)
        last_7d = now - timedelta(days=7)
        last_30d = now - timedelta(days=30)

        # Failed login stats from audit logs
        failed_logins_24h = await self._count_audit_logs(
            action="auth.login",
            status="failed",
            since=last_24h
        )

        failed_logins_7d = await self._count_audit_logs(
            action="auth.login",
            status="failed",
            since=last_7d
        )

        failed_logins_30d = await self._count_audit_logs(
            action="auth.login",
            status="failed",
            since=last_30d
        )

        # Locked accounts
        currently_locked = await self._count_currently_locked()
        locked_24h = await self._count_audit_logs(
            action="user.lock",
            since=last_24h
        )

        # Password security
        password_resets_24h = await self._count_audit_logs(
            action="auth.password_reset",
            since=last_24h
        )

        password_changes_24h = await self._count_audit_logs(
            action="auth.password_change",
            since=last_24h
        )

        # Account activity
        new_registrations_24h = await self._count_new_users(since=last_24h)
        email_verifications_24h = await self._count_audit_logs(
            action="user.verify_email",
            since=last_24h
        )

        # Top failed login IPs
        top_failed_login_ips = await self._get_top_failed_login_ips(since=last_7d, limit=10)

        # Top users with failed logins
        top_failed_login_users = await self._get_top_failed_login_users(limit=10)

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

    async def get_user_login_history(
        self,
        user_id: UUID,
        limit: int = 50
    ) -> Dict[str, Any]:
        """
        Get login history for a specific user.

        Args:
            user_id: User UUID
            limit: Number of recent login events (1-100)

        Returns:
            Dict with user info and login history

        Raises:
            ResourceNotFoundException: If user not found
        """
        # Get user
        user = await self._get_user_or_404(user_id)

        # Get login events from audit log
        events_result = await self.db.execute(
            select(AuditLog).where(
                AuditLog.user_id == user_id,
                AuditLog.action.like("auth.login%")
            ).order_by(AuditLog.created_at.desc()).limit(limit)
        )
        login_events = events_result.scalars().all()

        # Format login history
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
            "full_name": user.full_name,
            "email": user.email,
            "login_history": login_history,
            "total_events": len(login_history)
        }

    # ========================================================================
    # Private Helper Methods
    # ========================================================================

    async def _get_user_or_404(self, user_id: UUID) -> Users:
        """
        Get user or raise 404.

        Args:
            user_id: User UUID

        Returns:
            Users object

        Raises:
            ResourceNotFoundException: If user not found
        """
        result = await self.db.execute(
            select(Users).where(Users.id == user_id)
        )
        user = result.scalar_one_or_none()

        if not user:
            raise ResourceNotFoundException(
                resource_type="User",
                resource_id=str(user_id)
            )

        return user

    async def _count_audit_logs(
        self,
        action: str,
        status: Optional[str] = None,
        since: Optional[datetime] = None
    ) -> int:
        """
        Count audit logs matching criteria.

        Args:
            action: Audit log action
            status: Optional status filter
            since: Optional datetime filter

        Returns:
            Count of matching audit logs
        """
        query = select(func.count(AuditLog.id)).where(AuditLog.action == action)

        if status:
            query = query.where(AuditLog.status == status)

        if since:
            query = query.where(AuditLog.created_at >= since)

        result = await self.db.execute(query)
        return result.scalar() or 0

    async def get_user_security_stats(self, user_id: UUID) -> Dict[str, Any]:
        """
        Get security statistics for a specific user (user-scoped).

        Returns:
        - Failed login attempts count
        - Account lockout status
        - Last successful login
        - Last failed login
        - Password last changed
        - Active sessions count

        Args:
            user_id: User UUID

        Returns:
            Dict with user security statistics
        """
        # Get user
        user = await self._get_user_or_404(user_id)

        now = datetime.now(timezone.utc)
        is_locked = bool(user.locked_until and user.locked_until > now)

        # Get last successful login from audit logs
        last_login_query = select(AuditLog).where(
            and_(
                AuditLog.user_id == str(user_id),
                AuditLog.action == "user.login",
                AuditLog.status == "success"
            )
        ).order_by(AuditLog.created_at.desc()).limit(1)

        last_login_result = await self.db.execute(last_login_query)
        last_login = last_login_result.scalar_one_or_none()

        # Get last failed login from audit logs
        last_failed_query = select(AuditLog).where(
            and_(
                AuditLog.user_id == str(user_id),
                AuditLog.action == "user.login",
                AuditLog.status == "failure"
            )
        ).order_by(AuditLog.created_at.desc()).limit(1)

        last_failed_result = await self.db.execute(last_failed_query)
        last_failed = last_failed_result.scalar_one_or_none()

        # Count active sessions
        from src.api.models.user_models.user_sessions import UserSession
        active_sessions_query = select(func.count(UserSession.id)).where(
            and_(
                UserSession.user_id == user_id,
                UserSession.expires_at > now
            )
        )
        sessions_result = await self.db.execute(active_sessions_query)
        active_sessions = sessions_result.scalar() or 0

        return {
            "success": True,
            "data": {
                "user_id": str(user_id),
                "email": user.email,
                "failed_login_attempts": user.failed_login_attempts or 0,
                "is_locked": is_locked,
                "locked_until": user.locked_until.isoformat() if user.locked_until else None,
                "last_login": {
                    "timestamp": last_login.created_at.isoformat() if last_login else None,
                    "ip_address": last_login.metadata.get("ip_address") if last_login and last_login.metadata else None,
                    "user_agent": last_login.metadata.get("user_agent") if last_login and last_login.metadata else None
                } if last_login else None,
                "last_failed_login": {
                    "timestamp": last_failed.created_at.isoformat() if last_failed else None,
                    "ip_address": last_failed.metadata.get("ip_address") if last_failed and last_failed.metadata else None
                } if last_failed else None,
                "password_changed_at": user.password_changed_at.isoformat() if user.password_changed_at else None,
                "active_sessions_count": active_sessions,
                "account_created_at": user.created_at.isoformat() if user.created_at else None
            }
        }

    async def get_active_sessions_count(self, user_id: UUID) -> Dict[str, Any]:
        """
        Get count of active sessions for a user.

        Args:
            user_id: User UUID

        Returns:
            Dict with sessions count
        """
        from src.api.models.user_models.user_sessions import UserSession

        now = datetime.now(timezone.utc)
        query = select(func.count(UserSession.id)).where(
            and_(
                UserSession.user_id == user_id,
                UserSession.expires_at > now
            )
        )

        result = await self.db.execute(query)
        count = result.scalar() or 0

        return {
            "success": True,
            "data": {
                "user_id": str(user_id),
                "active_sessions_count": count
            }
        }

    async def _count_currently_locked(self) -> int:
        """
        Count currently locked accounts.

        Returns:
            Count of locked accounts
        """
        now = datetime.now(timezone.utc)
        result = await self.db.execute(
            select(func.count(Users.id)).where(
                Users.locked_until.isnot(None),
                Users.locked_until > now
            )
        )
        return result.scalar() or 0

    async def _count_new_users(self, since: datetime) -> int:
        """
        Count new user registrations since date.

        Args:
            since: Datetime to count from

        Returns:
            Count of new users
        """
        result = await self.db.execute(
            select(func.count(Users.id)).where(Users.created_at >= since)
        )
        return result.scalar() or 0

    async def _get_top_failed_login_ips(
        self,
        since: datetime,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Get top IPs with failed login attempts.

        Args:
            since: Datetime to search from
            limit: Maximum results

        Returns:
            List of dicts with ip and count
        """
        result = await self.db.execute(
            select(
                AuditLog.ip_address,
                func.count(AuditLog.id).label('count')
            ).where(
                AuditLog.action == "auth.login",
                AuditLog.status == "failed",
                AuditLog.created_at >= since,
                AuditLog.ip_address.isnot(None)
            ).group_by(AuditLog.ip_address).order_by(
                func.count(AuditLog.id).desc()
            ).limit(limit)
        )
        top_ips = result.all()

        return [
            {"ip": str(ip), "count": count}
            for ip, count in top_ips
        ]

    async def _get_top_failed_login_users(
        self,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Get top users with failed login attempts.

        Args:
            limit: Maximum results

        Returns:
            List of dicts with email and count
        """
        result = await self.db.execute(
            select(
                Users.email,
                Users.failed_login_attempts.label('count')
            ).where(
                Users.failed_login_attempts > 0
            ).order_by(Users.failed_login_attempts.desc()).limit(limit)
        )
        top_users = result.all()

        return [
            {"email": email, "count": count}
            for email, count in top_users
        ]
