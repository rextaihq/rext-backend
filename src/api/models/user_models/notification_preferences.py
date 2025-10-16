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

    # Email Notifications
    email_notifications = Column(Boolean, default=True, nullable=False)
    email_digest_frequency = Column(String(20), default="daily", nullable=False)  # instant, daily, weekly, never
    email_workspace_invites = Column(Boolean, default=True, nullable=False)
    email_comments = Column(Boolean, default=True, nullable=False)
    email_mentions = Column(Boolean, default=True, nullable=False)
    email_updates = Column(Boolean, default=False, nullable=False)

    # In-App Notifications
    in_app_notifications = Column(Boolean, default=True, nullable=False)
    in_app_workspace_invites = Column(Boolean, default=True, nullable=False)
    in_app_comments = Column(Boolean, default=True, nullable=False)
    in_app_mentions = Column(Boolean, default=True, nullable=False)
    in_app_updates = Column(Boolean, default=False, nullable=False)

    created_at = Column(TIMESTAMP, default=datetime.utcnow, nullable=False)
    updated_at = Column(TIMESTAMP, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    user = relationship("Users", back_populates="notification_preferences")

    def to_dict(self, **kwargs):
        """Convert to dictionary with camelCase keys for frontend."""
        data = super().to_dict(exclude=['id'], **kwargs)
        # Convert snake_case to camelCase for frontend
        return {
            "emailNotifications": data.get("email_notifications"),
            "emailDigestFrequency": data.get("email_digest_frequency"),
            "emailWorkspaceInvites": data.get("email_workspace_invites"),
            "emailComments": data.get("email_comments"),
            "emailMentions": data.get("email_mentions"),
            "emailUpdates": data.get("email_updates"),
            "inAppNotifications": data.get("in_app_notifications"),
            "inAppWorkspaceInvites": data.get("in_app_workspace_invites"),
            "inAppComments": data.get("in_app_comments"),
            "inAppMentions": data.get("in_app_mentions"),
            "inAppUpdates": data.get("in_app_updates"),
        }
