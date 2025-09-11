from sqlalchemy import Column, String, Boolean, ForeignKey, DateTime
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from src.api.database.database import Base
import uuid

class Projects(Base):
    __tablename__ = "projects"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=True, nullable=False)
    title = Column(String(80), nullable=False)
    memory_mode = Column(Boolean, nullable=False, default=False)  # ✅ Boolean instead of String
    instructions = Column(JSONB, nullable=True)  # ✅ More flexible than ARRAY(String)
    status = Column(String, nullable=False, default="process")

    # Relationships
    files = relationship("ProjectFiles", back_populates="project", cascade="all, delete-orphan")
    memories = relationship("Memories", back_populates="project", cascade="all, delete-orphan")


class ProjectFiles(Base):
    __tablename__ = "project_files"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=True, nullable=False)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    file_name = Column(String, nullable=False)
    file_type = Column(String, nullable=False)
    file_size = Column(String, nullable=False)
    file_path = Column(String, nullable=False)

    # Relationship back
    project = relationship("Projects", back_populates="files")


class Memories(Base):
    __tablename__ = "memories"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=True, nullable=False)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    memory_data = Column(JSONB, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now()) 
    
    # Relationship back
    project = relationship("Projects", back_populates="memories")
