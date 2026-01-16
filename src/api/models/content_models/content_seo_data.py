from sqlalchemy import Column, Text, Float, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from sqlalchemy.orm import relationship
from src.api.database.base import Base
from src.api.models.base import SerializableMixin
from datetime import datetime, timezone
import uuid


class ContentSEOData(Base, SerializableMixin):
    """SEO-specific data for content stored in separate table"""
    __tablename__ = "content_seo_data"

    content_id = Column(UUID(as_uuid=True), ForeignKey("content.id", ondelete="CASCADE"), primary_key=True)
    
    # SEO specific fields
    meta_title = Column(Text, nullable=True, comment="Meta title (50-60 chars)")
    meta_description = Column(Text, nullable=True, comment="Meta description (150-160 chars)")
    focus_keyphrase = Column(Text, nullable=True, comment="Primary focus keyphrase")
    keyphrase_density = Column(Float, nullable=True, comment="Keyphrase density percentage")
    secondary_keywords = Column(ARRAY(Text), nullable=True, comment="Secondary keywords")
    search_intent = Column(ARRAY(Text), nullable=True, comment="informational, navigational, etc.")
    
    # Scores
    seo_score = Column(Float, nullable=True)
    readability_score = Column(Float, nullable=True)
    seo_details = Column(Text, nullable=True, comment="Detailed SEO analysis/feedback")

    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=True, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    content = relationship("Content", back_populates="seo_data")
