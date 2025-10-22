from sqlalchemy import Column, String, Text, Integer, Float, DateTime, Boolean, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, ARRAY, JSONB
from sqlalchemy.orm import relationship
from src.api.database.base import Base
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
    status = Column(Text, nullable=True, default="draft")  # draft, pending_review, approved, rejected, published, archived
    content_language = Column(Text, nullable=True, default="English")

    # LangGraph workflow tracking
    langgraph_thread_id = Column(UUID(as_uuid=True), nullable=True, index=True,
                                  comment="LangGraph workflow thread ID for content generation tracking")

    # Consolidated JSONB columns (replaces 5 separate tables)
    metadata_json = Column(JSONB, nullable=True, comment="Content metadata (type, platform, audience, tone, etc.)")
    tracking_json = Column(JSONB, nullable=True, comment="Generation tracking (request_id, flow_execution_id, payloads)")
    ai_config_json = Column(JSONB, nullable=True, comment="AI configuration (model, temperature, params, errors)")
    structure_json = Column(JSONB, nullable=True, comment="Content structure (length, TOC, summary, CTA flags)")
    research_config_json = Column(JSONB, nullable=True, comment="Research configuration (level, fact-checking, freshness)")

    # Workflow tracking fields (added in migration 41596bee276b)
    published_at = Column(DateTime(timezone=True), nullable=True, comment="When content was published")
    submitted_for_review_at = Column(DateTime(timezone=True), nullable=True, comment="When content was submitted for review")
    reviewed_at = Column(DateTime(timezone=True), nullable=True, comment="When content was reviewed (approved/rejected)")
    reviewed_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, comment="Who reviewed the content")
    review_notes = Column(Text, nullable=True, comment="Feedback from reviewer")

    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=True, default=datetime.utcnow, onupdate=datetime.utcnow)
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    workspace = relationship("WorkspaceModel", back_populates="content_items")
    topic = relationship("TopicsModel", back_populates="content_items")
    created_by = relationship("Users", foreign_keys=[created_by_user_id])
    assigned_to = relationship("Users", foreign_keys=[assigned_to_user_id])
    author = relationship("Users", foreign_keys=[author_id])
    reviewed_by = relationship("Users", foreign_keys=[reviewed_by_user_id])
    featured_image = relationship("Media", foreign_keys=[featured_image_id], lazy="joined")

    # Related tables (kept separate for specific use cases)
    progress = relationship("ContentProgress", back_populates="content", uselist=False, cascade="all, delete-orphan")
    seo_data = relationship("ContentSEOData", back_populates="content", uselist=False, cascade="all, delete-orphan")
    reviews = relationship("ContentReview", back_populates="content", cascade="all, delete-orphan")
    versions = relationship("ContentVersion", back_populates="content", cascade="all, delete-orphan")

    # Deprecated relationships (tables dropped in migration 40fd95ca1e8d)
    # content_metadata, tracking, ai_config, structure, research_config → moved to JSONB columns

    # to_dict() inherited from SerializableMixin
