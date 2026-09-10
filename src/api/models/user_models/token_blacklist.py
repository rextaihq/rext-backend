"""
Token Blacklist Model

This model stores revoked/blacklisted JWT tokens to prevent their reuse.
Used for logout functionality and refresh token rotation.

When a token is blacklisted:
- Logout: User's access token is added to prevent reuse
- Refresh: Old refresh token is blacklisted after rotation
- Forced logout: Admin can revoke all user tokens
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from src.api.database.base import Base
from src.api.models.base import SerializableMixin


class TokenBlacklist(Base, SerializableMixin):
    """Store revoked/blacklisted tokens."""

    __tablename__ = "token_blacklist"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    jti = Column(String(255), unique=True, nullable=False)  # JWT ID (unique token identifier)
    token_type = Column(String(20), nullable=False)  # "access" or "refresh"
    user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )  # User who owned the token - cascade delete when user is removed
    revoked_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )  # When token was blacklisted
    expires_at = Column(
        DateTime(timezone=True), nullable=False
    )  # When token would naturally expire
    reason = Column(String(100))  # "logout", "refresh", "forced_logout", "password_change", etc.
    updated_at = Column(
        DateTime(timezone=True), onupdate=lambda: datetime.now(timezone.utc), nullable=True
    )

    # Relationships
    user = relationship("Users", back_populates="blacklisted_tokens")

    __table_args__ = (
        # Indexes for fast lookups
        Index("idx_token_blacklist_jti", "jti"),  # Primary lookup by JTI
        Index("idx_token_blacklist_user_id", "user_id"),  # Lookup by user
        Index("idx_token_blacklist_expires_at", "expires_at"),  # For cleanup jobs
    )

    # to_dict() inherited from SerializableMixin
