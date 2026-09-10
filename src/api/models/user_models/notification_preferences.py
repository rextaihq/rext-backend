import secrets
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from src.api.database.base import Base
from src.api.models.base import SerializableMixin

# ---------------------------------------------------------------------------
# Default values for all category-level notification preferences.
#
# Adding a new notification type only requires a new key here — no migration
# and no schema change needed.  Callers use get_preference(key) / set_preference(key, value).
# ---------------------------------------------------------------------------
DEFAULT_CATEGORY_PREFERENCES: dict[str, bool] = {
    # Workspace
    "ws_invite_received": True,
    "ws_invite_accepted": True,
    "ws_role_changed": True,
    "ws_member_removed": True,
    # Content Generation
    "gen_started": True,
    "gen_completed": True,
    "gen_failed": True,
    "gen_published": True,
    # Billing & Payments
    "billing_payment_success": True,
    "billing_payment_failed": True,
    "billing_subscription_cancelled": True,
    "billing_subscription_expiring": True,
    "billing_trial_ending": True,
    "billing_usage_limit_warning": True,
    "billing_usage_limit_exceeded": True,
    # Knowledge Base
    "kb_processing_completed": True,
    "kb_processing_failed": True,
    # Extended email/in-app category toggles (previously individual columns)
    "email_team_activity": True,
    "in_app_team_activity": True,
    "email_security_alerts": True,
    "in_app_security_alerts": True,
    "email_billing_updates": True,
    "in_app_billing_updates": True,
    "email_product_updates": False,
    "in_app_product_updates": False,
    "email_content_updates": True,
    "in_app_content_updates": True,
    "email_mentions": True,
    "in_app_mentions": True,
    "email_comments": True,
    "in_app_comments": True,
}


class NotificationPreferences(Base, SerializableMixin):
    """
    Notification preferences with JSONB-based category storage.

    Architecture decisions:
    - ``email_notifications`` and ``in_app_notifications`` remain dedicated columns
      because they are checked on every notification dispatch (hot path).
    - All other category-level boolean preferences are stored in a single JSONB
      column (``category_preferences``).  This eliminates the need for a schema
      migration every time a new notification type is introduced.
    - Use ``get_preference(key)`` / ``set_preference(key, value)`` instead of
      direct attribute access so that the JSONB mutation is detected by SQLAlchemy.
    """

    __tablename__ = "notification_preferences"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, nullable=False)
    user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )

    # ── Hot-path columns (checked on every notification dispatch) ──────────
    email_notifications = Column(Boolean, default=True, nullable=False)
    in_app_notifications = Column(Boolean, default=True, nullable=False)

    # ── Category preferences (all other boolean flags) ─────────────────────
    # server_default='{}' ensures rows created directly in SQL also get a valid value.
    category_preferences = Column(
        JSONB,
        nullable=False,
        default=lambda: dict(DEFAULT_CATEGORY_PREFERENCES),
        server_default="{}",
    )

    # ── Digest settings ────────────────────────────────────────────────────
    digest_enabled = Column(Boolean, default=True, nullable=False)
    digest_frequency = Column(
        String(20), default="daily", nullable=False
    )  # daily | weekly | monthly
    # Set by the digest scheduled task each time a digest email is sent, so the
    # next run can tell whether this user is due again for their cadence.
    digest_last_sent_at = Column(DateTime(timezone=True), nullable=True)

    # ── Marketing ─────────────────────────────────────────────────────────
    marketing_updates = Column(Boolean, default=False, nullable=False)
    unsubscribe_token = Column(
        String,
        unique=True,
        nullable=False,
        default=lambda: secrets.token_urlsafe(32),
    )

    # ── Timestamps ─────────────────────────────────────────────────────────
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # ── Relationship ───────────────────────────────────────────────────────
    user = relationship("Users", back_populates="notification_preferences")

    # ── JSONB accessor methods ─────────────────────────────────────────────

    def get_preference(self, key: str) -> bool:
        """
        Return the value of a category preference, falling back to the
        compiled default if the key is absent from the JSONB document.

        This is safe to call on newly-created rows before flush because
        ``DEFAULT_CATEGORY_PREFERENCES`` provides the fallback.
        """
        prefs = self.category_preferences or {}
        return prefs.get(key, DEFAULT_CATEGORY_PREFERENCES.get(key, True))

    def set_preference(self, key: str, value: bool) -> None:
        """
        Set a category preference value.

        IMPORTANT: we create a *new* dict rather than mutating in-place.
        SQLAlchemy tracks JSONB mutations via object identity, so in-place
        mutation (``self.category_preferences[key] = value``) is silently
        dropped unless MutableDict is used.  Reassignment avoids that pitfall.
        """
        current = (
            dict(self.category_preferences)
            if self.category_preferences
            else dict(DEFAULT_CATEGORY_PREFERENCES)
        )
        current[key] = value
        self.category_preferences = current

    # ── API response formatter ─────────────────────────────────────────────

    def to_dict(self, **kwargs) -> dict:
        """
        Return a backward-compatible API response shape.

        The nested structure mirrors the previous response exactly so that
        existing frontend consumers require no changes.
        """
        prefs = self.category_preferences or {}

        def _get(key: str, default: bool = True) -> bool:
            return prefs.get(key, DEFAULT_CATEGORY_PREFERENCES.get(key, default))

        return {
            "email_enabled": self.email_notifications,
            "in_app_enabled": self.in_app_notifications,
            "digest_enabled": self.digest_enabled,
            "digest_frequency": self.digest_frequency,
            "digest_last_sent_at": (
                self.digest_last_sent_at.isoformat() if self.digest_last_sent_at else None
            ),
            "workspace_notifications": {
                "invite_received": _get("ws_invite_received"),
                "invite_accepted": _get("ws_invite_accepted"),
                "role_changed": _get("ws_role_changed"),
                "member_removed": _get("ws_member_removed"),
            },
            "content_generation": {
                "generation_started": _get("gen_started"),
                "generation_completed": _get("gen_completed"),
                "generation_failed": _get("gen_failed"),
                "content_published": _get("gen_published"),
            },
            "billing": {
                "payment_success": _get("billing_payment_success"),
                "payment_failed": _get("billing_payment_failed"),
                "subscription_cancelled": _get("billing_subscription_cancelled"),
                "subscription_expiring": _get("billing_subscription_expiring"),
                "trial_ending": _get("billing_trial_ending"),
                "usage_limit_warning": _get("billing_usage_limit_warning"),
                "usage_limit_exceeded": _get("billing_usage_limit_exceeded"),
            },
            "knowledge_base": {
                "processing_completed": _get("kb_processing_completed"),
                "processing_failed": _get("kb_processing_failed"),
            },
            "marketing": {
                "marketing_updates": self.marketing_updates,
            },
        }
