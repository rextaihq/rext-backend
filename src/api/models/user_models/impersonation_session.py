"""Impersonation session model for tracking invalidated sessions."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, String
from sqlalchemy.dialects.postgresql import UUID

from src.api.database.base import Base
from src.api.models.base import SerializableMixin


class ImpersonationSession(Base, SerializableMixin):
    """
    Store invalidated impersonation sessions.

    When an admin stops impersonating a user, the session_id is stored here
    to prevent the old token from being used again.
    """

    __tablename__ = "impersonation_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(String(255), unique=True, nullable=False, index=True)
    is_valid = Column(Boolean, default=False, nullable=False)
    invalidated_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    def __repr__(self):
        return f"<ImpersonationSession(session_id={self.session_id}, is_valid={self.is_valid})>"
