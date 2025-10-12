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

    # Notification preferences
    workspace_invitation = Column(Boolean, default=True, nullable=False)
    invitation_accepted = Column(Boolean, default=True, nullable=False)
    role_changed = Column(Boolean, default=True, nullable=False)
    member_removed = Column(Boolean, default=True, nullable=False)
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
            "workspace_invitation": self.workspace_invitation,
            "invitation_accepted": self.invitation_accepted,
            "role_changed": self.role_changed,
            "member_removed": self.member_removed,
            "marketing": self.marketing,
            "unsubscribe_token": self.unsubscribe_token,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }
