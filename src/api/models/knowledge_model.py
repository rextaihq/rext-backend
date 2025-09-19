from sqlalchemy import Column, String, Integer, ForeignKey, Text, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from src.api.database.database import Base
import uuid

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
        base_dict = super().to_dict()

        # Add computed fields if needed
        base_dict.update({
            'processing_status': self.status,
            'content_metrics': {
                'char_count': self.char_count or 0,
                'word_count': self.word_count or 0,
                'estimated_reading_time': (self.word_count or 0) // 200  # ~200 WPM
            }
        })

        return base_dict

# File Knowledge
class KnowledgeFiles(Base):
    __tablename__ = "knowledge_files"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=True, nullable=False)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False)

    file_name = Column(String, nullable=False)
    file_type = Column(String, nullable=False)
    file_size = Column(Integer, nullable=False)
    file_path = Column(String, nullable=False)

    workspace = relationship("WorkspaceModel", back_populates="knowledge_files")

    def to_dict(self) -> dict:
        """Custom serialization for KnowledgeFiles model"""
        base_dict = super().to_dict()

        # Add file-specific metadata
        base_dict.update({
            'file_metadata': {
                'name': self.file_name,
                'type': self.file_type,
                'size_bytes': self.file_size,
                'size_mb': round(self.file_size / (1024 * 1024), 2),
                'path': self.file_path
            }
        })

        return base_dict


# Text Knowledge
class TextKnowledge(Base):
    __tablename__ = "text_knowledge"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=True, nullable=False)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False)

    # content
    content = Column(
        Text,
        nullable=False
    )

    workspace = relationship("WorkspaceModel", back_populates="text_knowledge")

    def to_dict(self) -> dict:
        """Custom serialization for TextKnowledge model"""
        base_dict = super().to_dict()

        # Add content analysis
        content_length = len(self.content or '')
        base_dict.update({
            'content_analysis': {
                'char_count': content_length,
                'word_count': len((self.content or '').split()),
                'paragraph_count': (self.content or '').count('\n\n') + 1,
                'is_empty': content_length == 0
            }
        })

        return base_dict