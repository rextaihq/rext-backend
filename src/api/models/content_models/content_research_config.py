from sqlalchemy import Column, Text, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from src.api.database.base import Base
from src.api.models.base import SerializableMixin
from datetime import datetime
import uuid


class ContentResearchConfig(Base, SerializableMixin):
    """Content research configuration"""
    __tablename__ = "content_research_config"

    content_id = Column(UUID(as_uuid=True), ForeignKey("content.id", ondelete="CASCADE"), primary_key=True)
    research_level = Column(Text, nullable=True)  # none, basic, standard, deep
    fact_checking = Column(Text, nullable=True)  # none, basic, rigorous
    content_freshness = Column(Text, nullable=True)  # any, recent, latest
    research_context = Column(JSONB, nullable=True)  # Research parameters and findings

    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=True, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    # Deprecated: This model is being phased out in favor of Content.research_config_json
    content = relationship("Content")
