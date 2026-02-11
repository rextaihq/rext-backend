import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Boolean, Integer, Text, DateTime,
    ForeignKey, UniqueConstraint
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from src.api.database.base import Base
from src.api.models.base import SerializableMixin, SoftDeleteMixin
from src.api.models.workspace_models.workspace_member import WorkspaceMembers

# -------------------------
# Users
# -------------------------
class Users(Base, SerializableMixin, SoftDeleteMixin):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=True, nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    full_name = Column(String(200))
    password_hash = Column(String(255), nullable=True)
    display_name = Column(String(200))
    bio = Column(String(500))
    password_changed_at = Column(DateTime(timezone=True))
    locked_until = Column(DateTime(timezone=True))
    reset_token = Column(Text)
    status = Column(String(20), default="active")
    email_verified = Column(Boolean, default=False)
    email_verified_at = Column(DateTime(timezone=True))
    last_login_at = Column(DateTime(timezone=True))
    login_count = Column(Integer, default=0)
    failed_login_attempts = Column(Integer, default=0)
    language = Column(String(10), default="en")
    timezone = Column(String(50), default="UTC")
    avatar_url = Column(String(500))
    provider_customer_id = Column(String(255), unique=True, index=True)  # Payment provider customer ID
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    deactivated_at = Column(DateTime(timezone=True))

    # Relationships
    user_roles = relationship("UserRole", back_populates="user", foreign_keys="UserRole.user_id", passive_deletes=True)
    workspace_memberships = relationship("WorkspaceMembers", back_populates="user", passive_deletes=True)
    workspaces = relationship("WorkspaceModel", foreign_keys="WorkspaceModel.user_id", back_populates="owner", passive_deletes=True)
    sent_invitations = relationship("UserInvitations", back_populates="invited_by", passive_deletes=True)
    assigned_roles = relationship("UserRole", back_populates="assigned_by", foreign_keys="UserRole.assigned_by_user_id", passive_deletes=True)
    sessions = relationship("UserSession", back_populates="user", cascade="all, delete-orphan", passive_deletes=True)
    notification_preferences = relationship("NotificationPreferences", back_populates="user", uselist=False, passive_deletes=True)
    blacklisted_tokens = relationship("TokenBlacklist", back_populates="user", cascade="all, delete-orphan", passive_deletes=True)
    email_preferences = relationship("EmailPreferences", back_populates="user", uselist=False, passive_deletes=True)
    preferences = relationship("UserPreferences", back_populates="user", uselist=False, cascade="all, delete-orphan", passive_deletes=True)
    media = relationship("Media", back_populates="user", cascade="all, delete-orphan", passive_deletes=True)
    oauth_accounts = relationship("OAuthAccount", back_populates="user", cascade="all, delete-orphan", passive_deletes=True)
    onboarding = relationship("UserOnboarding", back_populates="user", uselist=False, cascade="all, delete-orphan", passive_deletes=True)
    discount_usages = relationship("DiscountUsage", back_populates="user", cascade="all, delete-orphan", passive_deletes=True)
    refunds = relationship("Refund", back_populates="user", cascade="all, delete-orphan", passive_deletes=True)
    subscriptions = relationship("UserSubscription", back_populates="user", cascade="all, delete-orphan", passive_deletes=True)
    trial_conversions = relationship("TrialConversion", back_populates="user", cascade="all, delete-orphan", passive_deletes=True)
    licenses = relationship("License", back_populates="user", passive_deletes=True)
    payment_methods = relationship("PaymentMethod", back_populates="user", cascade="all, delete-orphan", passive_deletes=True)
    notifications = relationship("Notification", back_populates="user", cascade="all, delete-orphan", passive_deletes=True)

    # Admin invitation relationships
    sent_admin_invitations = relationship(
        "PlatformAdminInvitations",
        back_populates="invited_by",
        foreign_keys="PlatformAdminInvitations.invited_by_admin_id",
        passive_deletes=True
    )
    accepted_admin_invitations = relationship(
        "PlatformAdminInvitations",
        back_populates="accepted_by",
        foreign_keys="PlatformAdminInvitations.accepted_by_user_id",
        passive_deletes=True
    )
    revoked_admin_invitations = relationship(
        "PlatformAdminInvitations",
        back_populates="revoked_by",
        foreign_keys="PlatformAdminInvitations.revoked_by_admin_id",
        passive_deletes=True
    )

    def to_dict(self, **kwargs):
        """Exclude sensitive fields from serialization"""
        if 'exclude' not in kwargs:
            kwargs['exclude'] = ['password_hash', 'reset_token']
        return super().to_dict(**kwargs)
