from sqlalchemy import Column, String, Integer, ForeignKey, Text, CheckConstraint, DateTime
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from src.api.database.database import Base
import uuid
from datetime import datetime, timezone

# Brand Voice
class BrandVoice(Base):
    __tablename__ = "brand_voice"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=True, nullable=False)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False)

    about = Column(Text, nullable=True)
    customer_profile = Column(Text, nullable=True)
    selling_position = Column(Text, nullable=True)
    target_audience = Column(JSONB, nullable=True)
    brand_voice = Column(JSONB, nullable=True)
    competitors = Column(JSONB, nullable=True)
    content_strategy = Column(JSONB, nullable=True)

    workspace = relationship("WorkspaceModel", back_populates="brand_voices")

# Web Knowledge
class Website(Base):
    __tablename__ = "website"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=True, nullable=False)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False)

    url = Column(String, nullable=False)
    status = Column(String, nullable=False, default="process")
    char_count = Column(Integer, nullable=True)
    word_count = Column(Integer, nullable=True)

    workspace = relationship("WorkspaceModel", back_populates="websites")

    def to_dict(self) -> dict:
        """Custom serialization for Website model"""
        return {
            'id': str(self.id),
            'workspace_id': str(self.workspace_id),
            'url': self.url,
            'status': self.status,
            'char_count': self.char_count,
            'word_count': self.word_count,
            'processing_status': self.status,
            'content_metrics': {
                'char_count': self.char_count or 0,
                'word_count': self.word_count or 0,
                'estimated_reading_time': (self.word_count or 0) // 200  # ~200 WPM
            }
        }

# File Knowledge
class KnowledgeFiles(Base):
    __tablename__ = "knowledge_files"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=True, nullable=False)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False)

    file_name = Column(String, nullable=False)
    file_type = Column(String, nullable=False)
    file_size = Column(Integer, nullable=False)
    file_path = Column(String, nullable=False)
    status = Column(String, nullable=False, default="completed")
    char_count = Column(Integer, nullable=True)
    word_count = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    workspace = relationship("WorkspaceModel", back_populates="knowledge_files")

    def to_dict(self) -> dict:
        """Custom serialization for KnowledgeFiles model"""
        return {
            'id': str(self.id),
            'workspace_id': str(self.workspace_id),
            'name': self.file_name,
            'type': self.file_type,
            'size': self.file_size,
            'path': self.file_path,
            'file_path': self.file_path,
            'file_name': self.file_name,
            'file_type': self.file_type,
            'file_size': self.file_size,
            'status': self.status,
            'char_count': self.char_count,
            'word_count': self.word_count,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'file_metadata': {
                'name': self.file_name,
                'type': self.file_type,
                'size_bytes': self.file_size,
                'size_mb': round(self.file_size / (1024 * 1024), 2),
                'path': self.file_path
            }
        }


# Text Knowledge
class TextKnowledge(Base):
    __tablename__ = "text_knowledge"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=True, nullable=False)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False)

    title = Column(String, nullable=False, default="Untitled Note")
    content = Column(Text, nullable=False)
    tags = Column(JSONB, nullable=True)
    custom_metadata = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=lambda: datetime.now(timezone.utc), nullable=True)

    workspace = relationship("WorkspaceModel", back_populates="text_knowledge")

    def to_dict(self) -> dict:
        """Custom serialization for TextKnowledge model"""
        content_length = len(self.content or '')
        word_count = len((self.content or '').split())
        return {
            'id': str(self.id),
            'workspace_id': str(self.workspace_id),
            'title': self.title,
            'content': self.content,
            'tags': self.tags or [],
            'metadata': self.custom_metadata or {},
            'char_count': content_length,
            'word_count': word_count,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'content_analysis': {
                'char_count': content_length,
                'word_count': word_count,
                'paragraph_count': (self.content or '').count('\n\n') + 1,
                'is_empty': content_length == 0
            }
        }