"""
User Preferences Model

Stores user-specific preferences for UI customization and behavior.
"""

from sqlalchemy import Column, String, Integer, Boolean, DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid

from src.api.database.base import Base


class UserPreferences(Base):
    """User preferences for UI and behavior customization"""

    __tablename__ = "user_preferences"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)

    # Display preferences
    theme = Column(String(20), nullable=True, default="system")  # system, light, dark
    date_format = Column(String(20), nullable=True, default="iso")  # iso, us, eu, relative
    time_format = Column(String(20), nullable=True, default="24h")  # 24h, 12h
    items_per_page = Column(Integer, nullable=True, default=25)  # Pagination preference
    sidebar_collapsed = Column(Boolean, nullable=True, default=False)

    # Timestamps
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("Users", back_populates="preferences")

    # Indexes
    __table_args__ = (
        Index("ix_user_preferences_user_id", "user_id"),
    )

    def to_dict(self):
        """Convert to dictionary"""
        return {
            "id": str(self.id),
            "user_id": str(self.user_id),
            "theme": self.theme,
            "date_format": self.date_format,
            "time_format": self.time_format,
            "items_per_page": self.items_per_page,
            "sidebar_collapsed": self.sidebar_collapsed,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
