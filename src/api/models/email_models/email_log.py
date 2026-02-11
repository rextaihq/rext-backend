"""EmailLog Model - Tracks all email sends"""
from sqlalchemy import Column, String, DateTime, ForeignKey, Text, Integer
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid

from src.api.database.base import Base
from src.api.models.base import SerializableMixin


class EmailLog(Base, SerializableMixin):
    """
    EmailLog model for tracking all email sends.
    
    Tracks email lifecycle: queued -> sent -> delivered/failed/bounced
    Links to email_events for webhook tracking.
    """
    __tablename__ = "email_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspace.id", ondelete="SET NULL"), nullable=True, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    template_type = Column(String(100), nullable=True)  # e.g., "email_verification", "workspace_invitation"
    provider = Column(String(50), nullable=False)  # e.g., "resend", "smtp"
    provider_message_id = Column(String(255), nullable=True, index=True)  # Provider's message ID
    to_email = Column(String(255), nullable=False, index=True)
    from_email = Column(String(255), nullable=False)
    subject = Column(String(500), nullable=False)
    status = Column(String(50), nullable=False, default="queued", index=True)  # queued, sent, failed, delivered, bounced
    error_message = Column(Text, nullable=True)
    retry_count = Column(Integer, nullable=False, default=0)  # Number of retry attempts
    sent_at = Column(DateTime(timezone=True), nullable=True)
    delivered_at = Column(DateTime(timezone=True), nullable=True)
    failed_at = Column(DateTime(timezone=True), nullable=True)
    provider_response = Column(JSONB, nullable=True)  # Full provider response
    tags = Column(JSONB, nullable=True)  # Custom tags for categorization
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), index=True)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    events = relationship("EmailEvent", back_populates="email_log", cascade="all, delete-orphan")
    workspace = relationship("WorkspaceModel", foreign_keys=[workspace_id])
    user = relationship("Users", foreign_keys=[user_id])

    def __repr__(self):
        return f"<EmailLog(id={self.id}, to={self.to_email}, status={self.status}, provider={self.provider})>"
