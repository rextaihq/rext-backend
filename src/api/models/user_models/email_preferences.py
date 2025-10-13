"""
Email Preferences Model

User email notification preferences and unsubscribe management.
"""
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import relationship
from datetime import datetime
import secrets
import uuid

from src.api.database.database import Base


class EmailPreferences(Base):
    __tablename__ = "email_preferences"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)

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
    unsubscribe_token = Column(String, unique=True, nullable=False, default=lambda: secrets.token_urlsafe(32))

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    user = relationship("Users", back_populates="email_preferences", foreign_keys=[user_id])

    def to_dict(self):
        """Convert model to dictionary"""
        return {
            "id": str(self.id),
            "user_id": str(self.user_id),
            # Workspace notifications
            "workspace_invitation": self.workspace_invitation,
            "invitation_accepted": self.invitation_accepted,
            "role_changed": self.role_changed,
            "member_removed": self.member_removed,
            # Content generation
            "content_generation_started": self.content_generation_started,
            "content_generation_completed": self.content_generation_completed,
            "content_generation_failed": self.content_generation_failed,
            "content_published": self.content_published,
            # Billing
            "payment_succeeded": self.payment_succeeded,
            "payment_failed": self.payment_failed,
            "subscription_cancelled": self.subscription_cancelled,
            "subscription_expiring_soon": self.subscription_expiring_soon,
            "trial_ending_soon": self.trial_ending_soon,
            "usage_limit_warning": self.usage_limit_warning,
            "usage_limit_exceeded": self.usage_limit_exceeded,
            # Knowledge base
            "kb_processing_completed": self.kb_processing_completed,
            "kb_processing_failed": self.kb_processing_failed,
            # Digest
            "digest_enabled": self.digest_enabled,
            "digest_frequency": self.digest_frequency,
            # Marketing
            "marketing": self.marketing,
            # Token
            "unsubscribe_token": self.unsubscribe_token,
            # Timestamps
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }
