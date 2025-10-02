"""
User Session Model

Tracks active user sessions across devices for security and session management.
Stores session metadata like device info, IP address, and activity timestamps.
"""

import uuid
from datetime import datetime
from sqlalchemy import Column, String, Boolean, TIMESTAMP, Text, Index, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from src.api.database.database import Base


class UserSession(Base):
    """Store active user login sessions with device and location metadata."""
    __tablename__ = "user_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    jti = Column(String(255), unique=True, nullable=False, index=True)  # JWT ID from access token

    # Device/Client Information
    device_name = Column(String(255))  # e.g., "Chrome on Windows"
    device_type = Column(String(50))   # "desktop", "mobile", "tablet"
    user_agent = Column(Text)          # Full user agent string

    # Location Information
    ip_address = Column(String(45))    # IPv4 or IPv6
    country = Column(String(100))      # Optional: from IP geolocation
    city = Column(String(100))         # Optional: from IP geolocation

    # Session Status
    is_active = Column(Boolean, default=True, nullable=False, index=True)

    # Timestamps
    created_at = Column(TIMESTAMP, default=datetime.utcnow, nullable=False)
    last_activity_at = Column(TIMESTAMP, default=datetime.utcnow, nullable=False, index=True)
    expires_at = Column(TIMESTAMP, nullable=False)  # When access token expires
    revoked_at = Column(TIMESTAMP)     # When session was manually revoked

    # Additional metadata (flexible JSONB field)
    session_metadata = Column(JSONB, default=dict)  # For future extensibility

    # Relationships
    user = relationship("Users", back_populates="sessions")

    __table_args__ = (
        Index('idx_user_sessions_user_active', 'user_id', 'is_active'),
        Index('idx_user_sessions_jti', 'jti'),
        Index('idx_user_sessions_last_activity', 'last_activity_at'),
    )

    def to_dict(self):
        """Convert session to dictionary for API responses."""
        return {
            "id": str(self.id),
            "user_id": str(self.user_id),
            "device_name": self.device_name,
            "device_type": self.device_type,
            "ip_address": self.ip_address,
            "country": self.country,
            "city": self.city,
            "is_active": self.is_active,
            "is_current": False,  # Will be set by endpoint based on current token
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_activity_at": self.last_activity_at.isoformat() if self.last_activity_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
        }
