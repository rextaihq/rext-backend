from sqlalchemy import Column, Text, Float, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from sqlalchemy.orm import relationship
from src.api.database.database import Base
from datetime import datetime
import uuid


class ContentSEOData(Base):
    """SEO-specific data for content"""
    __tablename__ = "content_seo_data"

    content_id = Column(UUID(as_uuid=True), ForeignKey("content.id", ondelete="CASCADE"), primary_key=True)
    content_primary_keywords = Column(ARRAY(Text), nullable=False)
    content_secondary_keywords = Column(ARRAY(Text), nullable=True)
    content_meta_description = Column(Text, nullable=False)
    content_search_intent = Column(ARRAY(Text), nullable=True)  # informational, navigational, transactional, commercial
    content_seo_score = Column(Float, nullable=True)  # 0-100 score
    content_readability_score = Column(Float, nullable=True)  # Flesch reading ease or similar

    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=True, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    content = relationship("Content", back_populates="seo_data")
