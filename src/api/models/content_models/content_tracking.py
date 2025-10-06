from sqlalchemy import Column, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from src.api.database.database import Base
from src.api.models.base import SerializableMixin
from datetime import datetime
import uuid


class ContentTracking(Base, SerializableMixin):
    """Content generation tracking and audit trail"""
    __tablename__ = "content_tracking"

    content_id = Column(UUID(as_uuid=True), ForeignKey("content.id", ondelete="CASCADE"), primary_key=True)
    request_id = Column(UUID(as_uuid=True), nullable=True)  # Original request ID
    flow_execution_id = Column(UUID(as_uuid=True), nullable=True)  # Workflow execution ID
    request_payload = Column(JSONB, nullable=True)  # Original request data
    topic_snapshot = Column(JSONB, nullable=True)  # Snapshot of topic data at generation time

    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=True, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    content = relationship("Content", back_populates="tracking")
