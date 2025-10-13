import uuid
from datetime import datetime
from sqlalchemy import (
    Column, String, Boolean, Integer, Text, TIMESTAMP, DateTime,
    ForeignKey, UniqueConstraint
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from src.api.database.database import Base
from src.api.models.base import SerializableMixin
from src.api.models.workspace_models.workspace_member import WorkspaceMembers

# -------------------------
# Users
# -------------------------
class Users(Base, SerializableMixin):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=True, nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    username = Column(String(100), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    first_name = Column(String(100))
    last_name = Column(String(100))
    display_name = Column(String(200))
    password_changed_at = Column(TIMESTAMP)
    locked_until = Column(TIMESTAMP)
    reset_token = Column(Text)
    status = Column(String(20), default="active")
    email_verified = Column(Boolean, default=False)
    email_verified_at = Column(TIMESTAMP)
    last_login_at = Column(TIMESTAMP)
    login_count = Column(Integer, default=0)
    failed_login_attempts = Column(Integer, default=0)
    language = Column(String(10), default="en")
    timezone = Column(String(50), default="UTC")
    avatar_url = Column(String(500))
    provider_customer_id = Column(String(255), unique=True, index=True)  # Payment provider customer ID
    created_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)
    updated_at = Column(TIMESTAMP, default=datetime.utcnow, onupdate=datetime.utcnow)
    deactivated_at = Column(TIMESTAMP)
    deleted_at = Column(TIMESTAMP)

    # Relationships
    user_roles = relationship("UserRole", back_populates="user", foreign_keys="UserRole.user_id")
    workspace_memberships = relationship("WorkspaceMembers", back_populates="user")
    workspaces = relationship("WorkspaceModel", back_populates="owner")
    sent_invitations = relationship("UserInvitations", back_populates="invited_by")
    assigned_roles = relationship("UserRole", back_populates="assigned_by", foreign_keys="UserRole.assigned_by_user_id")
    notification_preferences = relationship("NotificationPreferences", back_populates="user", uselist=False)
    sessions = relationship("UserSession", back_populates="user", cascade="all, delete-orphan")
    email_preferences = relationship("EmailPreferences", back_populates="user", uselist=False, foreign_keys="EmailPreferences.user_id")
    media = relationship("Media", back_populates="user", cascade="all, delete-orphan")

    def to_dict(self, **kwargs):
        """Exclude sensitive fields from serialization"""
        if 'exclude' not in kwargs:
            kwargs['exclude'] = ['password_hash', 'reset_token']
        return super().to_dict(**kwargs)