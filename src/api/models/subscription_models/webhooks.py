"""Webhook event model for LemonSqueezy webhooks."""
import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, Boolean, Text, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID, JSONB
from src.api.database.base import Base
from src.api.models.base import SerializableMixin


class WebhookEvent(Base, SerializableMixin):
    """Webhook event model for tracking and ensuring idempotency."""
    __tablename__ = "webhook_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=True, nullable=False)

    # LemonSqueezy webhook details
    event_id = Column(String(255), nullable=False, unique=True, index=True)  # LemonSqueezy event ID
    event_name = Column(String(100), nullable=False, index=True)  # e.g., "subscription_created"

    # Event payload and processing
    payload = Column(JSONB, nullable=False)  # Full webhook payload
    processed = Column(Boolean, default=False, nullable=False, index=True)
    processed_at = Column(TIMESTAMP, nullable=True)

    # Error handling and retry tracking
    error_message = Column(Text, nullable=True)
    retry_count = Column(Integer, default=0, nullable=False)

    # Timestamps
    created_at = Column(TIMESTAMP, default=datetime.utcnow, nullable=False, index=True)
    updated_at = Column(TIMESTAMP, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<WebhookEvent(id={self.id}, event_id={self.event_id}, event_name={self.event_name}, processed={self.processed})>"

    def to_dict(self, **kwargs):
        """Custom serialization to handle payload."""
        data = super().to_dict(**kwargs)
        # Payload is already JSON-compatible
        return data
