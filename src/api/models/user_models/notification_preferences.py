import uuid
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from src.api.database.base import Base
from src.api.models.base import SerializableMixin
import secrets


class NotificationPreferences(Base, SerializableMixin):
    """
    Notification preferences aligned with frontend categories.
    """
    __tablename__ = "notification_preferences"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)

    # ==============================
    # GLOBAL TOGGLES
    # ==============================
    email_notifications = Column(Boolean, default=True, nullable=False)
    in_app_notifications = Column(Boolean, default=True, nullable=False)

    # ==============================
    # ACTIVITY & ALERTS
    # ==============================
    email_team_activity = Column(Boolean, default=True, nullable=False)
    in_app_team_activity = Column(Boolean, default=True, nullable=False)

    email_security_alerts = Column(Boolean, default=True, nullable=False)
    in_app_security_alerts = Column(Boolean, default=True, nullable=False)

    email_billing_updates = Column(Boolean, default=True, nullable=False)
    in_app_billing_updates = Column(Boolean, default=True, nullable=False)

    email_product_updates = Column(Boolean, default=True, nullable=False)
    in_app_product_updates = Column(Boolean, default=True, nullable=False)

    email_content_updates = Column(Boolean, default=True, nullable=False)
    in_app_content_updates = Column(Boolean, default=True, nullable=False)

    email_mentions = Column(Boolean, default=True, nullable=False)
    in_app_mentions = Column(Boolean, default=True, nullable=False)

    email_comments = Column(Boolean, default=True, nullable=False)
    in_app_comments = Column(Boolean, default=True, nullable=False)

    # ==============================
    # WORKSPACE NOTIFICATIONS
    # ==============================
    ws_invite_received = Column(Boolean, default=True, nullable=False)
    ws_invite_accepted = Column(Boolean, default=True, nullable=False)
    ws_role_changed = Column(Boolean, default=True, nullable=False)
    ws_member_removed = Column(Boolean, default=True, nullable=False)

    # ==============================
    # CONTENT GENERATION
    # ==============================
    gen_started = Column(Boolean, default=True, nullable=False)
    gen_completed = Column(Boolean, default=True, nullable=False)
    gen_failed = Column(Boolean, default=True, nullable=False)
    gen_published = Column(Boolean, default=True, nullable=False)

    # ==============================
    # BILLING & PAYMENTS
    # ==============================
    billing_payment_success = Column(Boolean, default=True, nullable=False)
    billing_payment_failed = Column(Boolean, default=True, nullable=False)
    billing_subscription_cancelled = Column(Boolean, default=True, nullable=False)
    billing_subscription_expiring = Column(Boolean, default=True, nullable=False)
    billing_trial_ending = Column(Boolean, default=True, nullable=False)
    billing_usage_limit_warning = Column(Boolean, default=True, nullable=False)
    billing_usage_limit_exceeded = Column(Boolean, default=True, nullable=False)

    # ==============================
    # KNOWLEDGE BASE
    # ==============================
    kb_processing_completed = Column(Boolean, default=True, nullable=False)
    kb_processing_failed = Column(Boolean, default=True, nullable=False)

    # ==============================
    # EMAIL DIGEST
    # ==============================
    digest_enabled = Column(Boolean, default=True, nullable=False)
    digest_frequency = Column(String(20), default="daily", nullable=False)  # daily, weekly, monthly

    # ==============================
    # MARKETING COMMUNICATIONS
    # ==============================
    marketing_updates = Column(Boolean, default=False, nullable=False)
    unsubscribe_token = Column(
        String,
        unique=True,
        nullable=False,
        default=lambda: secrets.token_urlsafe(32)
    )
    # ==============================
    # TIMESTAMPS
    # ==============================
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False
    )

    # Relationship
    user = relationship("Users", back_populates="notification_preferences")

    def to_dict(self, **kwargs):
        """API response formatter matching the frontend spec."""
        return {
            "email_enabled": self.email_notifications,
            "in_app_enabled": self.in_app_notifications,
            "digest_enabled": self.digest_enabled,
            "digest_frequency": self.digest_frequency,
            "categories": {
                "mentions": self.email_mentions or self.in_app_mentions,
                "workspace_invites": self.ws_invite_received,
                "content_updates": self.email_content_updates or self.in_app_content_updates,
                "comments": self.email_comments or self.in_app_comments,
                "team_activity": self.email_team_activity or self.in_app_team_activity,
                "security_alerts": self.email_security_alerts or self.in_app_security_alerts,
                "billing_updates": self.email_billing_updates or self.in_app_billing_updates,
                "product_updates": self.email_product_updates or self.in_app_product_updates,
            }
        }
