"""User onboarding model."""

import uuid
from datetime import datetime
from typing import List

from sqlalchemy import Column, Boolean, DateTime, Integer, JSON, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from src.api.database.base import Base
from src.api.models.base import SerializableMixin


class UserOnboarding(Base, SerializableMixin):
    """
    Model for tracking user onboarding progress.

    Tracks completion of onboarding steps to guide new users through
    the initial setup process.
    """

    __tablename__ = "user_onboarding"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=True, nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False, index=True)

    # Onboarding status
    completed = Column(Boolean, default=False, nullable=False, index=True)
    current_step = Column(Integer, default=0, nullable=False)

    # Step tracking (list of step numbers/names)
    completed_steps = Column(JSON, default=list, nullable=False)
    skipped_steps = Column(JSON, default=list, nullable=False)

    # Timestamps
    started_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    user = relationship("Users", back_populates="onboarding")

    def __repr__(self) -> str:
        """String representation."""
        return f"<UserOnboarding(user_id={self.user_id}, completed={self.completed}, current_step={self.current_step})>"
