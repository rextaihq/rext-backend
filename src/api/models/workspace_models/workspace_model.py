from datetime import datetime, timezone
import uuid
from typing import Optional, List
from sqlalchemy import String, ForeignKey
from sqlalchemy.orm import relationship, Mapped, mapped_column
from src.api.database.base import Base
from src.api.models.base import SerializableMixin
from src.api.models.mixins import UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin


# -------------------------
# Workspace
# -------------------------
class WorkspaceModel(Base, SerializableMixin, UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "workspace"

    # id, created_at, updated_at, deleted_at provided by mixins
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    slug: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    timezone: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # IANA timezone identifier
    url: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    deleted_by: Mapped[Optional[uuid.UUID]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)

    # Relationships
    owner = relationship("Users", foreign_keys=[user_id], back_populates="workspaces")
    user_roles = relationship("UserRole", back_populates="workspace")
    members = relationship("WorkspaceMembers", back_populates="workspace", cascade="all, delete-orphan", passive_deletes=True)
    invitations = relationship("UserInvitations", back_populates="workspace", passive_deletes=True)
    email_templates = relationship("EmailTemplate", back_populates="workspace", cascade="all, delete-orphan", passive_deletes=True)

    # Other related entities
    brand_voices = relationship("BrandVoice", back_populates="workspace", cascade="all, delete-orphan", passive_deletes=True)
    personas = relationship("Persona", back_populates="workspace", cascade="all, delete-orphan", passive_deletes=True)
    knowledge_bases = relationship("KnowledgeBase", back_populates="workspace", cascade="all, delete-orphan", passive_deletes=True)
    websites = relationship("Website", back_populates="workspace", cascade="all, delete-orphan", passive_deletes=True)
    knowledge_files = relationship("KnowledgeFiles", back_populates="workspace", cascade="all, delete-orphan", passive_deletes=True)
    text_knowledge = relationship("TextKnowledge", back_populates="workspace", cascade="all, delete-orphan", passive_deletes=True)
    content_items = relationship("Content", back_populates="workspace", cascade="all, delete-orphan", passive_deletes=True)
    media = relationship("Media", back_populates="workspace", cascade="all, delete-orphan", passive_deletes=True)
    topics = relationship("TopicsModel", back_populates="workspace", cascade="all, delete-orphan", passive_deletes=True)
    notifications = relationship("Notification", back_populates="workspace", cascade="all, delete-orphan", passive_deletes=True)
    integrations = relationship("WorkspaceIntegration", back_populates="workspace", cascade="all, delete-orphan", passive_deletes=True)

    
