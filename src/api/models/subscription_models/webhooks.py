"""Webhook event model for LemonSqueezy webhooks."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from src.api.database.base import Base
from src.api.models.base import SerializableMixin


class WebhookEvent(Base, SerializableMixin):
    """Webhook event model for tracking and ensuring idempotency."""

    __tablename__ = "webhook_events"

    id = Column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=True, nullable=False
    )

    # LemonSqueezy webhook details
    event_id = Column(String(255), nullable=False, unique=True, index=True)  # LemonSqueezy event ID
    event_name = Column(String(100), nullable=False, index=True)  # e.g., "subscription_created"

    # Event payload and processing
    payload = Column(JSONB, nullable=False)  # Full webhook payload
    processed = Column(Boolean, default=False, nullable=False, index=True)
    processed_at = Column(DateTime(timezone=True), nullable=True)

    # Error handling and retry tracking
    error_message = Column(Text, nullable=True)
    retry_count = Column(Integer, default=0, nullable=False)

    # Timestamps
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    def __repr__(self):
        return f"<WebhookEvent(id={self.id}, event_id={self.event_id}, event_name={self.event_name}, processed={self.processed})>"

    def to_dict(self, include_payload: bool = False, **kwargs):
        """Serialize WebhookEvent with payload excluded by default."""
        exclude = list(kwargs.pop("exclude", []))
        if not include_payload and "payload" not in exclude:
            exclude.append("payload")

        data = super().to_dict(exclude=exclude, **kwargs)
        return data
