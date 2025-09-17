from sqlalchemy import Column, String,Text,DateTime, func   
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from src.api.database.database import Base
import uuid

class WorkspaceModel(Base):
    __tablename__ = "workspace"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=True, nullable=False)
    title = Column(String, nullable=False, unique=True)
    description = Column(Text, nullable=True)
    url = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)

    brand_voices = relationship("BrandVoice", back_populates="workspace", cascade="all, delete-orphan")
    websites = relationship("Website", back_populates="workspace", cascade="all, delete-orphan")
    knowledge_files = relationship("KnowledgeFiles", back_populates="workspace", cascade="all, delete-orphan")

