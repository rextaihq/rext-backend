import uuid
from typing import Optional

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.api.database.base import Base
from src.api.models.base import SerializableMixin
from src.api.models.mixins import SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin


# -------------------------
# Workspace
# -------------------------
class WorkspaceModel(Base, SerializableMixin, UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin):
    __tablename__ = "workspace"

    # id, created_at, updated_at, deleted_at provided by mixins
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    slug: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    timezone: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True
    )  # IANA timezone identifier
    url: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # The site's favicon in the media store (an object name, resolved to a URL when
    # served), fetched when the workspace is created or its brand voice refreshed.
    favicon_url: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    deleted_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # Relationships
    owner = relationship("Users", foreign_keys=[user_id], back_populates="workspaces")
    user_roles = relationship("UserRole", back_populates="workspace")
    members = relationship(
        "WorkspaceMembers",
        back_populates="workspace",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    invitations = relationship("UserInvitations", back_populates="workspace", passive_deletes=True)
    email_templates = relationship(
        "EmailTemplate",
        back_populates="workspace",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    # Other related entities
    brand_voices = relationship(
        "BrandVoice", back_populates="workspace", cascade="all, delete-orphan", passive_deletes=True
    )
    personas = relationship(
        "Persona", back_populates="workspace", cascade="all, delete-orphan", passive_deletes=True
    )
    knowledge_bases = relationship(
        "KnowledgeBase",
        back_populates="workspace",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    websites = relationship(
        "Website", back_populates="workspace", cascade="all, delete-orphan", passive_deletes=True
    )
    knowledge_files = relationship(
        "KnowledgeFiles",
        back_populates="workspace",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    text_knowledge = relationship(
        "TextKnowledge",
        back_populates="workspace",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    content_items = relationship(
        "Content", back_populates="workspace", cascade="all, delete-orphan", passive_deletes=True
    )
    notifications = relationship(
        "Notification",
        back_populates="workspace",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    integrations = relationship(
        "WorkspaceIntegration",
        back_populates="workspace",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
