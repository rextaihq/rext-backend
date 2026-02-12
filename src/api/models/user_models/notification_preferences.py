import uuid
from sqlalchemy import Column, String, Boolean, TIMESTAMP, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime
from src.api.database.base import Base
from src.api.models.base import SerializableMixin


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

    # ==============================
    # TIMESTAMPS
    # ==============================
    created_at = Column(TIMESTAMP, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        TIMESTAMP,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False
    )

    # Relationship
    user = relationship("Users", back_populates="notification_preferences")

    def to_dict(self, **kwargs):
        """API response formatter."""
        data = super().to_dict(exclude=['id', 'user_id'], **kwargs)

        return {
            "email_enabled": self.email_notifications,
            "in_app_enabled": self.in_app_notifications,
            "digest_enabled": self.digest_enabled,
            "digest_frequency": self.digest_frequency,
            "workspace_notifications": {
                "invite_received": data["ws_invite_received"],
                "invite_accepted": data["ws_invite_accepted"],
                "role_changed": data["ws_role_changed"],
                "member_removed": data["ws_member_removed"],
            },
            "content_generation": {
                "generation_started": data["gen_started"],
                "generation_completed": data["gen_completed"],
                "generation_failed": data["gen_failed"],
                "content_published": data["gen_published"],
            },
            "billing": {
                "payment_success": data["billing_payment_success"],
                "payment_failed": data["billing_payment_failed"],
                "subscription_cancelled": data["billing_subscription_cancelled"],
                "subscription_expiring": data["billing_subscription_expiring"],
                "trial_ending": data["billing_trial_ending"],
                "usage_limit_warning": data["billing_usage_limit_warning"],
                "usage_limit_exceeded": data["billing_usage_limit_exceeded"],
            },
            "knowledge_base": {
                "processing_completed": data["kb_processing_completed"],
                "processing_failed": data["kb_processing_failed"],
            },
            "marketing": {
                "marketing_updates": data["marketing_updates"]
            }
        }
