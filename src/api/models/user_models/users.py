import uuid
from datetime import datetime
from sqlalchemy import (
    Column, String, Boolean, Integer, Text, TIMESTAMP, DateTime,
    ForeignKey, UniqueConstraint
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from src.api.database.database import Base


# -------------------------
# Users
# -------------------------
class Users(Base):
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
    created_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)
    updated_at = Column(TIMESTAMP, default=datetime.utcnow, onupdate=datetime.utcnow)
    deleted_at = Column(TIMESTAMP)

    # Relationships
    user_roles = relationship("UserRole", back_populates="user", foreign_keys="UserRole.user_id")
    workspace_memberships = relationship("WorkspaceMembers", back_populates="user")
    workspaces = relationship("WorkspaceModel", back_populates="owner")
    sent_invitations = relationship("UserInvitations", back_populates="invited_by")
    assigned_roles = relationship("UserRole", back_populates="assigned_by", foreign_keys="UserRole.assigned_by_user_id")

    def to_dict(self):
        return {
            "id": str(self.id),
            "email": self.email,
            "username": self.username,
            "first_name": self.first_name,
            "last_name": self.last_name,
            "display_name": self.display_name,
            "status": self.status,
            "email_verified": self.email_verified,
            "language": self.language,
            "timezone": self.timezone,
            "avatar_url": self.avatar_url,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }