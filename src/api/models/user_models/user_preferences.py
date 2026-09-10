"""
User Preferences Model

Stores user-specific preferences for UI customization and behavior.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from src.api.database.base import Base
from src.api.models.base import SerializableMixin


class UserPreferences(Base, SerializableMixin):
    """User preferences for UI and behavior customization"""

    __tablename__ = "user_preferences"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True
    )

    # Display preferences
    theme = Column(String(20), nullable=True, default="system")  # system, light, dark
    date_format = Column(String(20), nullable=True, default="iso")  # iso, us, eu, relative
    time_format = Column(String(20), nullable=True, default="24h")  # 24h, 12h
    items_per_page = Column(Integer, nullable=True, default=25)  # Pagination preference
    sidebar_collapsed = Column(Boolean, nullable=True, default=False)

    # Timestamps
    created_at = Column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    user = relationship("Users", back_populates="preferences")
