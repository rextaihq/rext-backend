import uuid
from datetime import datetime
from sqlalchemy import (
    Column, String, Boolean, Integer, Text, TIMESTAMP, DateTime,
    ForeignKey, UniqueConstraint
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from src.api.database.base import Base
from src.api.models.base import SerializableMixin
from src.api.models.workspace_models.workspace_member import WorkspaceMembers

# -------------------------
# Users
# -------------------------
class Users(Base, SerializableMixin):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=True, nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    full_name = Column(String(200))
    password_hash = Column(String(255), nullable=False)
    display_name = Column(String(200))
    bio = Column(String(500))
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
    workspaces = relationship("WorkspaceModel", foreign_keys="WorkspaceModel.user_id", back_populates="owner")
    sent_invitations = relationship("UserInvitations", back_populates="invited_by")
    assigned_roles = relationship("UserRole", back_populates="assigned_by", foreign_keys="UserRole.assigned_by_user_id")
    notification_preferences = relationship("NotificationPreferences", back_populates="user", uselist=False)
    sessions = relationship("UserSession", back_populates="user", cascade="all, delete-orphan")
    email_preferences = relationship("EmailPreferences", back_populates="user", uselist=False)
    preferences = relationship("UserPreferences", back_populates="user", uselist=False, cascade="all, delete-orphan")
    media = relationship("Media", back_populates="user", cascade="all, delete-orphan")
    oauth_accounts = relationship("OAuthAccount", back_populates="user", cascade="all, delete-orphan")
    onboarding = relationship("UserOnboarding", back_populates="user", uselist=False, cascade="all, delete-orphan")
    discount_usages = relationship("DiscountUsage", back_populates="user", cascade="all, delete-orphan")
    refunds = relationship("Refund", back_populates="user", cascade="all, delete-orphan")
    notifications = relationship("Notification", back_populates="user", cascade="all, delete-orphan")

    # Admin invitation relationships
    sent_admin_invitations = relationship(
        "PlatformAdminInvitations",
        back_populates="invited_by",
        foreign_keys="PlatformAdminInvitations.invited_by_admin_id"
    )
    accepted_admin_invitations = relationship(
        "PlatformAdminInvitations",
        back_populates="accepted_by",
        foreign_keys="PlatformAdminInvitations.accepted_by_user_id"
    )
    revoked_admin_invitations = relationship(
        "PlatformAdminInvitations",
        back_populates="revoked_by",
        foreign_keys="PlatformAdminInvitations.revoked_by_admin_id"
    )

    def to_dict(self, **kwargs):
        """Exclude sensitive fields from serialization"""
        if 'exclude' not in kwargs:
            kwargs['exclude'] = ['password_hash', 'reset_token']
        return super().to_dict(**kwargs)