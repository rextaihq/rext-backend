"""
Email Preferences Model

User email notification preferences and unsubscribe management.
"""

import secrets
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import relationship

from src.api.database.base import Base
from src.api.models.base import SerializableMixin


class EmailPreferences(Base, SerializableMixin):
    __tablename__ = "email_preferences"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    # Workspace notification preferences
    workspace_invitation = Column(Boolean, default=True, nullable=False)
    invitation_accepted = Column(Boolean, default=True, nullable=False)
    role_changed = Column(Boolean, default=True, nullable=False)
    member_removed = Column(Boolean, default=True, nullable=False)

    # Content generation preferences
    content_generation_started = Column(Boolean, default=True, nullable=False)
    content_generation_completed = Column(Boolean, default=True, nullable=False)
    content_generation_failed = Column(Boolean, default=True, nullable=False)
    content_published = Column(Boolean, default=True, nullable=False)

    # Billing preferences
    payment_succeeded = Column(Boolean, default=True, nullable=False)
    payment_failed = Column(Boolean, default=True, nullable=False)
    subscription_cancelled = Column(Boolean, default=True, nullable=False)
    subscription_expiring_soon = Column(Boolean, default=True, nullable=False)
    trial_ending_soon = Column(Boolean, default=True, nullable=False)
    usage_limit_warning = Column(Boolean, default=True, nullable=False)
    usage_limit_exceeded = Column(Boolean, default=True, nullable=False)

    # Knowledge base preferences
    kb_processing_completed = Column(Boolean, default=True, nullable=False)
    kb_processing_failed = Column(Boolean, default=True, nullable=False)

    # Digest preferences
    digest_enabled = Column(Boolean, default=False, nullable=False)
    digest_frequency = Column(String(20), default="weekly", nullable=False)

    # Marketing preferences
    marketing = Column(Boolean, default=False, nullable=False)

    # Unsubscribe token
    unsubscribe_token = Column(
        String, unique=True, nullable=False, default=lambda: secrets.token_urlsafe(32)
    )

    # Timestamps
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    user = relationship("Users", back_populates="email_preferences", foreign_keys=[user_id])

    def to_dict(self, **kwargs):
        """Serialize preferences, excluding the unsubscribe token by default."""
        if "exclude" not in kwargs:
            kwargs["exclude"] = ["unsubscribe_token"]
        return super().to_dict(**kwargs)
