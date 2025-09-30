from sqlalchemy import Column, String,Text,DateTime, func,ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from src.api.database.database import Base
from datetime import datetime
import uuid

# -------------------------
# Workspace
# -------------------------
class WorkspaceModel(Base):
    __tablename__ = "workspace"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=True, nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    name = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    url = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=True, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    owner = relationship("Users", back_populates="workspaces")
    user_roles = relationship("UserRole", back_populates="workspace")
    members = relationship("WorkspaceMembers", back_populates="workspace",cascade="all, delete-orphan")
    invitations = relationship("UserInvitations", back_populates="workspace")

    # Other related entities
    brand_voices = relationship("BrandVoice", back_populates="workspace", cascade="all, delete-orphan")
    websites = relationship("Website", back_populates="workspace", cascade="all, delete-orphan")
    knowledge_files = relationship("KnowledgeFiles", back_populates="workspace", cascade="all, delete-orphan")
    text_knowledge = relationship("TextKnowledge", back_populates="workspace", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": str(self.id),
            "user_id": str(self.user_id),
            "name": self.name,
            "description": self.description,
            "url": self.url,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }