import uuid
from sqlalchemy import Column, String, Boolean, TIMESTAMP, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime
from src.api.database.base import Base
from src.api.models.base import SerializableMixin


class NotificationPreferences(Base, SerializableMixin):
    """
    User notification preferences model.

    Stores user preferences for email and in-app notifications.
    Each user has one set of notification preferences (one-to-one relationship).
    """
    __tablename__ = "notification_preferences"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)

    # Global toggles
    email_notifications = Column(Boolean, default=True, nullable=False)
    in_app_notifications = Column(Boolean, default=True, nullable=False)

    # Digest settings
    digest_enabled = Column(Boolean, default=True, nullable=False)
    email_digest_frequency = Column(String(20), default="daily", nullable=False)  # daily, weekly, monthly

    # Category-specific preferences (email)
    email_mentions = Column(Boolean, default=True, nullable=False)
    email_workspace_invites = Column(Boolean, default=True, nullable=False)
    email_content_updates = Column(Boolean, default=True, nullable=False)
    email_comments = Column(Boolean, default=True, nullable=False)
    email_team_activity = Column(Boolean, default=True, nullable=False)
    email_security_alerts = Column(Boolean, default=True, nullable=False)
    email_billing_updates = Column(Boolean, default=True, nullable=False)
    email_product_updates = Column(Boolean, default=False, nullable=False)

    # Category-specific preferences (in-app)
    in_app_mentions = Column(Boolean, default=True, nullable=False)
    in_app_workspace_invites = Column(Boolean, default=True, nullable=False)
    in_app_content_updates = Column(Boolean, default=True, nullable=False)
    in_app_comments = Column(Boolean, default=True, nullable=False)
    in_app_team_activity = Column(Boolean, default=True, nullable=False)
    in_app_security_alerts = Column(Boolean, default=True, nullable=False)
    in_app_billing_updates = Column(Boolean, default=True, nullable=False)
    in_app_product_updates = Column(Boolean, default=False, nullable=False)

    created_at = Column(TIMESTAMP, default=datetime.utcnow, nullable=False)
    updated_at = Column(TIMESTAMP, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    user = relationship("Users", back_populates="notification_preferences")

    def to_dict(self, **kwargs):
        """Convert to dictionary matching the API spec format.

        Note: Categories return True if enabled for either email OR in-app.
        This provides a simplified view while maintaining backward compatibility.
        """
        data = super().to_dict(exclude=['id', 'user_id', 'created_at', 'updated_at'], **kwargs)
        categories = {
            "mentions": data.get("email_mentions") or data.get("in_app_mentions"),
            "workspace_invites": data.get("email_workspace_invites") or data.get("in_app_workspace_invites"),
            "content_updates": data.get("email_content_updates") or data.get("in_app_content_updates"),
            "comments": data.get("email_comments") or data.get("in_app_comments"),
            "team_activity": data.get("email_team_activity") or data.get("in_app_team_activity"),
            "security_alerts": data.get("email_security_alerts") or data.get("in_app_security_alerts"),
            "billing_updates": data.get("email_billing_updates") or data.get("in_app_billing_updates"),
            "product_updates": data.get("email_product_updates") or data.get("in_app_product_updates")
        }

        # Keep all original fields, and add the API-format categories
        return {**data, "categories": categories}