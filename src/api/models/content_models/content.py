from sqlalchemy import Column, String, Text, Integer, Float, DateTime, Boolean, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, ARRAY, JSONB
from sqlalchemy.orm import relationship
from src.api.database.base import Base
from src.api.models.base import SerializableMixin
from datetime import datetime
import uuid


class Content(Base, SerializableMixin):
    """Main content table - stores core content and metadata"""
    __tablename__ = "content"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=True, nullable=False)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False, index=True)
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

    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=True, default=datetime.utcnow, onupdate=datetime.utcnow)
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    workspace = relationship("WorkspaceModel", back_populates="content_items")
    created_by = relationship("Users", foreign_keys=[created_by_user_id])
    seo_data = relationship("ContentSEOData", back_populates="content", uselist=False, cascade="all, delete-orphan")

    def to_dict(self, **kwargs):
        return super().to_dict(**kwargs)
