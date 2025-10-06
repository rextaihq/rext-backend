from sqlalchemy import Column, String, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from sqlalchemy.orm import relationship
from src.api.database.database import Base
from src.api.models.base import SerializableMixin
from datetime import datetime
import uuid


class ContentReview(Base, SerializableMixin):
    """Content review and approval workflow"""
    __tablename__ = "content_review"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=True, nullable=False)
    content_id = Column(UUID(as_uuid=True), ForeignKey("content.id", ondelete="CASCADE"), nullable=False, unique=True)
    content_type = Column(String(50), nullable=False)
    assigned_reviewers = Column(ARRAY(UUID(as_uuid=True)), nullable=True)  # Array of user IDs
    status = Column(String(20), nullable=True)  # pending, approved, rejected, changes_requested
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=False)

    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=True, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    content = relationship("Content", back_populates="reviews")
    creator = relationship("Users", foreign_keys=[created_by])
