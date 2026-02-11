"""EmailEvent Model - Tracks webhook events from email providers"""
from sqlalchemy import Column, String, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
import uuid

from src.api.database.base import Base
from src.api.models.base import SerializableMixin


class EmailEvent(Base, SerializableMixin):
    """
    EmailEvent model for tracking webhook events from email providers.
    
    Tracks email lifecycle events: delivered, opened, clicked, bounced, complained
    Links back to email_logs for correlation.
    """
    __tablename__ = "email_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email_log_id = Column(UUID(as_uuid=True), ForeignKey("email_logs.id", ondelete="SET NULL"), nullable=True, index=True)
    provider = Column(String(50), nullable=False)  # e.g., "resend"
    provider_event_id = Column(String(255), nullable=False, unique=True)  # Provider's event ID
    provider_message_id = Column(String(255), nullable=False, index=True)  # Links to email_logs
    event_type = Column(String(50), nullable=False, index=True)  # delivered, opened, clicked, bounced, complained
    event_data = Column(JSONB, nullable=True)  # Full webhook payload
    received_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    # Relationships
    email_log = relationship("EmailLog", back_populates="events")

    def __repr__(self):
        return f"<EmailEvent(id={self.id}, type={self.event_type}, provider={self.provider})>"
