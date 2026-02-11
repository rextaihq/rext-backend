"""
Session Service - Business Logic for User Session Management

This service encapsulates all business logic related to user session
management, including session listing, revocation, and token blacklisting.

Responsibilities:
- List active user sessions
- Revoke individual sessions
- Revoke all sessions for a user
- Token blacklisting for logout

Does NOT:
- Handle HTTP requests/responses (that's routes)
- Commit transactions (that's decorators/routes)
- Generate tokens (that's auth service)
"""

from typing import List, Dict, Any, Union
from uuid import UUID
from datetime import datetime, timezone, timedelta

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.api.models.user_models.user_sessions import UserSession
from src.api.models.user_models.token_blacklist import TokenBlacklist
from src.utils.logger import logger
from src.api.middleware.exceptions import ResourceNotFoundException


class SessionService:
    """Service for user session management"""

    def __init__(self, db: AsyncSession):
        """
        Initialize SessionService.

        Args:
            db: Async database session
        """
        self.db = db

    async def list_user_sessions(self, user_id: UUID) -> List[Dict[str, Any]]:
        """
        List all active sessions for a user.

        Args:
            user_id: User UUID

        Returns:
            List of session dicts with device info
        """
        result = await self.db.execute(
            select(UserSession).where(
                UserSession.user_id == user_id,
                UserSession.is_active.is_(True)
            ).order_by(UserSession.created_at.desc())
        )
        sessions = result.scalars().all()

        sessions_data = []
        for session in sessions:
            sessions_data.append({
                "id": str(session.id),
                "device_name": session.device_name,
                "device_type": session.device_type,
                "ip_address": str(session.ip_address) if session.ip_address else None,
                "user_agent": session.user_agent,
                "created_at": session.created_at.isoformat() if session.created_at else None,
                "last_activity_at": session.last_activity_at.isoformat() if session.last_activity_at else None,
                "is_current": False,  # Will be determined by route based on current token
                "token_id": session.jti,
            })

        return sessions_data

    async def revoke_session(
        self,
        user_id: UUID,
        session_id: UUID
    ) -> Dict[str, str]:
        """
        Revoke a specific user session.

        Business Rules:
        - Session must belong to user
        - Blacklists the session's token
        - Marks session as inactive

        Args:
            user_id: User UUID
            session_id: Session UUID to revoke

        Returns:
            Dict with revoked session info

        Raises:
            ResourceNotFoundException: If session not found
        """
        # Get session
        result = await self.db.execute(
            select(UserSession).where(
                UserSession.id == session_id,
                UserSession.user_id == user_id
            )
        )
        session = result.scalar_one_or_none()

        if not session:
            raise ResourceNotFoundException(
                resource_type="UserSession",
                resource_id=str(session_id),
                message="Session not found or does not belong to user"
            )

        # Blacklist token
        if session.jti:
            blacklist_entry = TokenBlacklist(
                jti=session.jti,
                token_type="access",
                user_id=user_id,
                revoked_at=datetime.now(timezone.utc),
                expires_at=self._normalize_expiry(session.expires_at),
                reason="session_revoked"
            )
            self.db.add(blacklist_entry)

        # Deactivate session
        session.is_active = False
        session.revoked_at = datetime.now(timezone.utc)

        await self.db.flush()

        logger.info(
            f"Session {session_id} revoked for user {user_id}",
            extra={"session_id": str(session_id), "user_id": str(user_id)}
        )

        return {
            "session_id": str(session_id),
            "revoked": True,
            "revoked_at": session.revoked_at.isoformat()
        }

    async def revoke_all_sessions(
        self,
        user_id: UUID,
        exclude_session_id: UUID = None,
        exclude_session_jti: str = None
    ) -> int:
        """
        Revoke all sessions for a user.

        Business Rules:
        - Can exclude current session
        - Blacklists all session tokens
        - Marks all sessions as inactive

        Args:
            user_id: User UUID
            exclude_session_id: Optional session to keep active

        Returns:
            Count of revoked sessions
        """
        # Get all active sessions
        query = select(UserSession).where(
            UserSession.user_id == user_id,
            UserSession.is_active.is_(True)
        )

        if exclude_session_id:
            query = query.where(UserSession.id != exclude_session_id)
        if exclude_session_jti:
            query = query.where(UserSession.jti != exclude_session_jti)

        result = await self.db.execute(query)
        sessions = result.scalars().all()

        revoked_count = 0
        now = datetime.now(timezone.utc)

        for session in sessions:
            # Blacklist token
            if session.jti:
                blacklist_entry = TokenBlacklist(
                    jti=session.jti,
                    token_type="access",
                    user_id=user_id,
                    revoked_at=now,
                    expires_at=self._normalize_expiry(session.expires_at),
                    reason="all_sessions_revoked"
                )
                self.db.add(blacklist_entry)

            # Deactivate session
            session.is_active = False
            session.revoked_at = now
            revoked_count += 1

        await self.db.flush()

        logger.info(
            f"Revoked {revoked_count} sessions for user {user_id}",
            extra={"user_id": str(user_id), "count": revoked_count}
        )

        return revoked_count

    @staticmethod
    def _normalize_expiry(expires_at: Union[datetime, float, int, None]) -> datetime:
        """Coerce stored expiry value into a datetime object."""
        if isinstance(expires_at, datetime):
            return expires_at
        if isinstance(expires_at, (int, float)):
            return datetime.fromtimestamp(expires_at, tz=timezone.utc)
        return datetime.now(timezone.utc)
