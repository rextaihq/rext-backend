from sqlalchemy import Column, String, func, DateTime, Boolean, ForeignKey
from src.api.models.content_models import Content
from sqlalchemy.dialects.postgresql import UUID, ARRAY, JSONB
from sqlalchemy.orm import relationship
from src.api.database.base import Base
from src.api.models.base import SerializableMixin
import uuid

class TopicsModel(Base, SerializableMixin):
    __tablename__ = "topics"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=True, nullable=False)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False, index=True)
    generated_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    topic_name = Column(String, nullable=False) # Rename back to topic_name
    description = Column(String, nullable=True) # Description was nullable in baseline

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=True)

    # Relationships
    workspace = relationship("WorkspaceModel", back_populates="topics")
    content_items = relationship("Content", back_populates="topic")
    generated_by = relationship("Users", foreign_keys=[generated_by_user_id], backref="topics_generated")

    def to_dict(self) -> dict:
        """Simple serialization for Topics model"""
        return {
            "id": str(self.id),
            "workspace_id": str(self.workspace_id),
            "generated_by_user_id": str(self.generated_by_user_id) if self.generated_by_user_id else None,
            "topic_name": self.topic_name,
            "description": self.description,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }