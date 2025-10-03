from sqlalchemy import Column, Boolean, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from src.api.database.database import Base
from datetime import datetime
import uuid


class ContentStructure(Base):
    """Content structure configuration"""
    __tablename__ = "content_structure"

    content_id = Column(UUID(as_uuid=True), ForeignKey("content.id", ondelete="CASCADE"), primary_key=True)
    content_length = Column(JSONB, nullable=True)  # {min_words, max_words, target_words}
    include_toc = Column(Boolean, default=False)  # Table of contents
    include_summary = Column(Boolean, default=False)  # Executive summary
    include_cta = Column(Boolean, default=False)  # Call to action
    include_key_takeaways = Column(Boolean, default=False)
    include_latest_info = Column(Boolean, default=False)  # Include latest news/data
    include_examples = Column(Boolean, default=False)
    include_statistics = Column(Boolean, default=False)
    include_quotes = Column(Boolean, default=False)
    competitor_analysis = Column(Boolean, default=False)

    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=True, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    content = relationship("Content", back_populates="structure")
