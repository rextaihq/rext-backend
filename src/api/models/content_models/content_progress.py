from sqlalchemy import Column, Text, Integer, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from src.api.database.database import Base
from src.api.models.base import SerializableMixin
from datetime import datetime
import uuid


class ContentProgress(Base, SerializableMixin):
    """Content generation progress tracking"""
    __tablename__ = "content_progress"

    content_id = Column(UUID(as_uuid=True), ForeignKey("content.id", ondelete="CASCADE"), primary_key=True)
    current_step = Column(Text, nullable=False)  # researching, outlining, writing, refining, finalizing
    progress_percent = Column(Integer, default=0)
    status_message = Column(Text, nullable=True)
    step_details = Column(JSONB, nullable=True)  # JSON with step-specific data
    estimated_time_remaining = Column(Integer, nullable=True)  # seconds

    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=True, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    content = relationship("Content", back_populates="progress")
