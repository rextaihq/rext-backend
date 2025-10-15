from sqlalchemy import Column, String, Text, Integer, Float, DateTime, Boolean, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, ARRAY, JSONB
from sqlalchemy.orm import relationship
from src.api.database.database import Base
from src.api.models.base import SerializableMixin
from datetime import datetime
import uuid


class Content(Base, SerializableMixin):
    """Main content table - stores generated content"""
    __tablename__ = "content"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=True, nullable=False)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False, index=True)
    topic_id = Column(UUID(as_uuid=True), ForeignKey("topics.id", ondelete="SET NULL"), nullable=True, index=True)
    created_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=False, index=True)
    assigned_to_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    author_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    featured_image_id = Column(UUID(as_uuid=True), ForeignKey("media.id", ondelete="SET NULL"), nullable=True, index=True)

    title = Column(Text, nullable=False)
    slug = Column(Text, unique=True, nullable=False, index=True)
    body_markdown = Column(Text, nullable=True)
    body_html = Column(Text, nullable=True)
    content_format = Column(Text, nullable=True, default="Markdown")  # Markdown, HTML, Plain Text
    status = Column(Text, nullable=True, default="draft")  # draft, generating, ready, published, archived
    content_language = Column(Text, nullable=True, default="English")

    # LangGraph workflow tracking
    langgraph_thread_id = Column(UUID(as_uuid=True), nullable=True, index=True,
                                  comment="LangGraph workflow thread ID for content generation tracking")

    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=True, default=datetime.utcnow, onupdate=datetime.utcnow)
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    workspace = relationship("WorkspaceModel", back_populates="content_items")
    topic = relationship("TopicsModel", back_populates="content_items")
    created_by = relationship("Users", foreign_keys=[created_by_user_id])
    assigned_to = relationship("Users", foreign_keys=[assigned_to_user_id])
    author = relationship("Users", foreign_keys=[author_id])
    featured_image = relationship("Media", foreign_keys=[featured_image_id], lazy="joined")

    # Related tables
    progress = relationship("ContentProgress", back_populates="content", uselist=False, cascade="all, delete-orphan")
    content_metadata = relationship("ContentMetadata", back_populates="content", uselist=False, cascade="all, delete-orphan")
    seo_data = relationship("ContentSEOData", back_populates="content", uselist=False, cascade="all, delete-orphan")
    ai_config = relationship("ContentAIConfig", back_populates="content", uselist=False, cascade="all, delete-orphan")
    structure = relationship("ContentStructure", back_populates="content", uselist=False, cascade="all, delete-orphan")
    research_config = relationship("ContentResearchConfig", back_populates="content", uselist=False, cascade="all, delete-orphan")
    tracking = relationship("ContentTracking", back_populates="content", uselist=False, cascade="all, delete-orphan")
    reviews = relationship("ContentReview", back_populates="content", cascade="all, delete-orphan")
    versions = relationship("ContentVersion", back_populates="content", cascade="all, delete-orphan")

    # to_dict() inherited from SerializableMixin
