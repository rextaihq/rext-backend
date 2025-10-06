from sqlalchemy import Column, Text, Integer, DateTime, Numeric, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from src.api.database.database import Base
from src.api.models.base import SerializableMixin
from datetime import datetime
import uuid


class ContentAIConfig(Base, SerializableMixin):
    """AI generation configuration and results"""
    __tablename__ = "content_ai_config"

    content_id = Column(UUID(as_uuid=True), ForeignKey("content.id", ondelete="CASCADE"), primary_key=True)
    ai_model = Column(Text, nullable=False)  # gpt-4, claude-3, etc.
    temperature = Column(Numeric(3, 2), nullable=True)  # 0.00 - 2.00
    max_output_tokens = Column(Integer, nullable=True)
    top_p = Column(Numeric(3, 2), nullable=True)  # 0.00 - 1.00
    frequency_penalty = Column(Numeric(3, 2), nullable=True)  # -2.00 - 2.00
    generation_params = Column(JSONB, nullable=True)  # Additional model-specific parameters
    context_sources = Column(JSONB, nullable=True)  # Sources used for context (knowledge base, URLs, etc.)
    generation_errors = Column(JSONB, nullable=True)  # Array of error objects if generation failed
    generation_warnings = Column(JSONB, nullable=True)  # Array of warning objects
    structured_output = Column(JSONB, nullable=True)  # Structured data extracted from generation
    generated_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    content = relationship("Content", back_populates="ai_config")
