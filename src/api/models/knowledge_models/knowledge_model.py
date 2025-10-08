from sqlalchemy import Column, String, Integer, ForeignKey, Text, CheckConstraint, DateTime
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from src.api.database.database import Base
from src.api.models.base import SerializableMixin
import uuid
from datetime import datetime, timezone

# Brand Voice
class BrandVoice(Base, SerializableMixin):
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
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=lambda: datetime.now(timezone.utc), nullable=True)

    workspace = relationship("WorkspaceModel", back_populates="brand_voices")

# Web Knowledge
class Website(Base, SerializableMixin):
    __tablename__ = "website"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=True, nullable=False)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False)

    url = Column(String, nullable=False)
    status = Column(String, nullable=False, default="process")
    char_count = Column(Integer, nullable=True)
    word_count = Column(Integer, nullable=True)

    workspace = relationship("WorkspaceModel", back_populates="websites")

    def to_dict(self, **kwargs) -> dict:
        """Custom serialization with computed fields"""
        data = super().to_dict(**kwargs)
        # Add custom computed fields
        data['processing_status'] = self.status
        data['content_metrics'] = {
            'char_count': self.char_count or 0,
            'word_count': self.word_count or 0,
            'estimated_reading_time': (self.word_count or 0) // 200  # ~200 WPM
        }
        return data

# File Knowledge
class KnowledgeFiles(Base, SerializableMixin):
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

    # Security fields
    file_hash = Column(String(64), nullable=True, index=True)  # SHA-256 hash for duplicate detection
    mime_type = Column(String(100), nullable=True)  # Detected MIME type (magic number)
    chunk_count = Column(Integer, nullable=True)  # Number of vector chunks

    workspace = relationship("WorkspaceModel", back_populates="knowledge_files")

    def to_dict(self, **kwargs) -> dict:
        """Custom serialization with computed fields and aliases"""
        data = super().to_dict(**kwargs)
        # Add aliases for backward compatibility
        data['name'] = data.get('file_name')
        data['type'] = data.get('file_type')
        data['size'] = data.get('file_size')
        data['path'] = data.get('file_path')
        # Add computed file_metadata
        data['file_metadata'] = {
            'name': self.file_name,
            'type': self.file_type,
            'size_bytes': self.file_size,
            'size_mb': round(self.file_size / (1024 * 1024), 2),
            'path': self.file_path,
            'hash': self.file_hash,
            'mime_type': self.mime_type
        }
        return data


# Text Knowledge
class TextKnowledge(Base, SerializableMixin):
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

    def to_dict(self, **kwargs) -> dict:
        """Custom serialization with computed content analysis"""
        data = super().to_dict(**kwargs)
        # Add alias for custom_metadata
        data['metadata'] = self.custom_metadata or {}
        # Compute content metrics
        content_length = len(self.content or '')
        word_count = len((self.content or '').split())
        data['char_count'] = content_length
        data['word_count'] = word_count
        data['content_analysis'] = {
            'char_count': content_length,
            'word_count': word_count,
            'paragraph_count': (self.content or '').count('\n\n') + 1,
            'is_empty': content_length == 0
        }
        return data