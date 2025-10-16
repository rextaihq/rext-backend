from sqlalchemy import Column, Text, Integer, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, ARRAY, JSONB
from sqlalchemy.orm import relationship
from src.api.database.base import Base
from src.api.models.base import SerializableMixin
from datetime import datetime
import uuid


class ContentMetadata(Base, SerializableMixin):
    """Content metadata and configuration"""
    __tablename__ = "content_metadata"

    content_id = Column(UUID(as_uuid=True), ForeignKey("content.id", ondelete="CASCADE"), primary_key=True)
    content_summary = Column(Text, nullable=True)
    content_type = Column(Text, nullable=True)  # blog_post, article, social_post, email, etc.
    target_platform = Column(Text, nullable=True)  # Medium, LinkedIn, WordPress, etc.
    target_industry = Column(Text, nullable=True)
    target_audience = Column(ARRAY(Text), nullable=True)
    audience_size = Column(Text, nullable=True)  # small, medium, large, enterprise
    complexity_level = Column(Text, nullable=True)  # beginner, intermediate, advanced, expert
    content_tone = Column(ARRAY(Text), nullable=True)  # professional, casual, friendly, authoritative, etc.
    target_region = Column(Text, nullable=True)
    content_objectives = Column(ARRAY(Text), nullable=True)  # educate, persuade, inform, entertain, etc.
    source_references = Column(ARRAY(Text), nullable=True)  # URLs or citations
    content_word_count = Column(Integer, nullable=True)
    reading_time_minutes = Column(Integer, nullable=True)
    content_quality_scores = Column(JSONB, nullable=True)  # JSON with various quality metrics
    featured_image_prompt = Column(Text, nullable=True)
    featured_image_alt_text = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=True, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    # Deprecated: This model is being phased out in favor of Content.metadata_json
    content = relationship("Content")
