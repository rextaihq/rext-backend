from sqlalchemy import Column, String, Integer, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from src.api.database.database import Base
import uuid


class KnowledgeModel(Base):
    __tablename__ = "knowledge"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=True, nullable=False)
    title = Column(String, nullable=False)
    description = Column(String, nullable=True)

    # Relationships
    brand_voices = relationship("BrandVoice", back_populates="knowledge", cascade="all, delete-orphan")
    websites = relationship("Website", back_populates="knowledge", cascade="all, delete-orphan")
    project_files = relationship("KnowledgeFiles", back_populates="knowledge", cascade="all, delete-orphan")


class BrandVoice(Base):
    __tablename__ = "brand_voice"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=True, nullable=False)
    knowledge_id = Column(UUID(as_uuid=True), ForeignKey("knowledge.id", ondelete="CASCADE"), nullable=False)

    about = Column(String, nullable=True)
    customer_profile = Column(String, nullable=True)
    selling_position = Column(String, nullable=True)
    target_audience = Column(JSONB, nullable=True)
    brand_voice = Column(JSONB, nullable=True)
    competitors = Column(JSONB, nullable=True)
    content_strategy = Column(JSONB, nullable=True)

    knowledge = relationship("KnowledgeModel", back_populates="brand_voices")


class Website(Base):
    __tablename__ = "website"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=True, nullable=False)
    knowledge_id = Column(UUID(as_uuid=True), ForeignKey("knowledge.id", ondelete="CASCADE"), nullable=False)

    url = Column(String, nullable=True)
    status = Column(String, nullable=False, default="process")
    char_count = Column(Integer, nullable=True)
    word_count = Column(Integer, nullable=True)

    knowledge = relationship("KnowledgeModel", back_populates="websites")


class KnowledgeFiles(Base):
    __tablename__ = "knowledge_files"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=True, nullable=False)
    knowledge_id = Column(UUID(as_uuid=True), ForeignKey("knowledge.id", ondelete="CASCADE"), nullable=False)

    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    file_name = Column(String, nullable=False)
    file_type = Column(String, nullable=False)
    file_size = Column(String, nullable=False)
    file_path = Column(String, nullable=False)

    knowledge = relationship("KnowledgeModel", back_populates="project_files")
