from sqlalchemy import Column, String,DateTime,func,Boolean
from sqlalchemy.dialects.postgresql import UUID, ARRAY, JSONB
from src.api.database.database import Base
import uuid

class Topics(Base):
    __tablename__ = "topics"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=True, nullable=False)
    title = Column(String, nullable=False)
    angle = Column(String, nullable=False)
    description = Column(String, nullable=False)  # New field
    channel_fit = Column(ARRAY(String), nullable=False)
    audience_fit = Column(ARRAY(String), nullable=False)
    why_it_works = Column(String, nullable=True)
    scores = Column(JSONB, nullable=False)
    tags = Column(ARRAY(String), nullable=True)
    suggested_defaults = Column(JSONB, nullable=False)  # New field
    goal_alignment = Column(JSONB, nullable=False)  # New field
    content_guidance = Column(JSONB, nullable=False)  # New field
    audience_insights = Column(JSONB, nullable=False)  # New field
    internal_research_config = Column(JSONB, nullable=False)  # New field
    user_settings = Column(JSONB, nullable=False)  # New field
    status = Column(Boolean, nullable=True, server_default="true")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False) # New field
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False) # New field

