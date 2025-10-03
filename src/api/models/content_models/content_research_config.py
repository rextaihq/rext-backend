from sqlalchemy import Column, Text, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from src.api.database.database import Base
from datetime import datetime
import uuid


class ContentResearchConfig(Base):
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
    content = relationship("Content", back_populates="research_config")
