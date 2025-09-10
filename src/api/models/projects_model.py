from sqlalchemy import Column, String, Float
from sqlalchemy.dialects.postgresql import UUID, ARRAY, JSONB
from src.api.database.database import Base
import uuid

class Projects(Base):
    __tablename__ = "projects"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=True, nullable=False)
    title = Column(String(80), nullable=False) 
    memory_mode = Column(String, nullable=False, default="false")  
    instructions = Column(ARRAY(String), nullable=False)
    file= Column(JSONB, nullable=True)
    status = Column(String, nullable=False, default="process")