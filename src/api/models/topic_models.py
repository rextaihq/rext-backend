from sqlalchemy import Column, String, Float
from sqlalchemy.dialects.postgresql import UUID, ARRAY, JSONB
from src.api.database.database import Base
import uuid

class Topics(Base):
    __tablename__ = "topics"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=True, nullable=False)
    title = Column(String(80), nullable=False) 
    angle = Column(String, nullable=False)      
    channel_fit = Column(ARRAY(String), nullable=False) 
    audience_fit = Column(ARRAY(String), nullable=False) 
    why_it_works = Column(String, nullable=True)  
    scores = Column(JSONB, nullable=False)       
    tags = Column(ARRAY(String), nullable=True)  
