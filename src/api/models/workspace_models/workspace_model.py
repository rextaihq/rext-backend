from sqlalchemy import Column, String, DateTime, func, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from src.api.database.base import Base
from src.api.models.base import SerializableMixin, SoftDeleteMixin
from datetime import datetime, timezone
import uuid

# -------------------------
# Workspace
# -------------------------
class WorkspaceModel(Base, SerializableMixin, SoftDeleteMixin):
    __tablename__ = "workspace"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=True, nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name = Column(String, nullable=False)
    slug = Column(String, unique=True, nullable=False, index=True)
    timezone = Column(String(50), nullable=True)  # IANA timezone identifier (e.g., America/New_York, UTC)
    url = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=True, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    deleted_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)  # User who deleted

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
    notifications = relationship("Notification", back_populates="workspace", cascade="all, delete-orphan", passive_deletes=True)
    integrations = relationship("WorkspaceIntegration", back_populates="workspace", cascade="all, delete-orphan", passive_deletes=True)

    