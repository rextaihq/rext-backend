from sqlalchemy import Column, String, Text, Integer, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, ARRAY, JSONB
from sqlalchemy.orm import relationship
from src.api.database.base import Base
from src.api.models.base import SerializableMixin
from src.api.models.mixins import UUIDPrimaryKeyMixin, TimestampMixin, WorkspaceScopedMixin, SoftDeleteMixin


class Content(Base, SerializableMixin, UUIDPrimaryKeyMixin, TimestampMixin, WorkspaceScopedMixin, SoftDeleteMixin):
    """Main content table - stores core content and metadata"""
    __tablename__ = "content"

    # id, workspace_id, created_at, updated_at, deleted_at provided by mixins
    created_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=False, index=True)

    # Core content fields
    title = Column(Text, nullable=False,unique=True)
    slug = Column(Text, unique=True, nullable=False, index=True)
    introduction = Column(Text, nullable=True)
    body_markdown = Column(Text, nullable=True)
    body_html = Column(Text, nullable=True)
    
    # Metadata and Status
    status = Column(Text, nullable=True, default="draft")
    content_language = Column(Text, nullable=True, default="English")
    tags = Column(ARRAY(Text), nullable=True, comment="Tags (common to content)")

    # LangGraph workflow tracking
    langgraph_thread_id = Column(UUID(as_uuid=True), nullable=True, index=True)

    # Media and Schema (remaining on content for now)
    images_data = Column(JSONB, nullable=True, comment="Inline images data")
    links_data = Column(JSONB, nullable=True, comment="Internal and outbound links")
    schema_markup = Column(JSONB, nullable=True, comment="Structured data/schema markup")
    
    # WordPress publishing fields
    wordpress_post_id = Column(Integer, nullable=True)
    wordpress_url = Column(Text, nullable=True)
    wordpress_published_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    workspace = relationship("WorkspaceModel", back_populates="content_items")
    created_by = relationship("Users", foreign_keys=[created_by_user_id])
    seo_data = relationship("ContentSEOData", back_populates="content", uselist=False, cascade="all, delete-orphan", passive_deletes=True)
    media_items = relationship("ContentMedia", back_populates="content", cascade="all, delete-orphan", passive_deletes=True)
