from sqlalchemy import Column, String, Float
from sqlalchemy.dialects.postgresql import UUID, ARRAY, JSONB
from src.api.database.database import Base
import uuid

class Topics(Base):
    __tablename__ = "topics"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=True, nullable=False)
    title = Column(String(80), nullable=False)  # <80 chars
    angle = Column(String, nullable=False)      # 1-sentence unique take
    channel_fit = Column(ARRAY(String), nullable=False)  # selected channels
    audience_fit = Column(ARRAY(String), nullable=False) # selected personas
    why_it_works = Column(String, nullable=True)  # short reason
    scores = Column(JSONB, nullable=False)        # { relevance, freshness, novelty }
    tags = Column(ARRAY(String), nullable=True)   # ["tutorial","explainer","news",...]
