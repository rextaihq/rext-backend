from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from src.api.database.base import Base
from src.api.models.base import SerializableMixin
from datetime import datetime, timezone
import uuid


class Integration(Base, SerializableMixin):
    """
    Connected Site Model
    
    Stores WordPress integration credentials for workspaces.
    """
    __tablename__ = "integrations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=True, nullable=False)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False, index=True)
    integration_type = Column(String(50), nullable=False, default="wordpress", index=True)
    is_active = Column(Boolean, default=True, nullable=False)

    # WordPress specific fields
    site_url = Column(String(500), nullable=True, comment="WordPress site URL")
    api_endpoint = Column(String(500), nullable=True, comment="Rext-AI Plugin Base Endpoint")
    username = Column(String(255), nullable=True, comment="WordPress username")
    app_password = Column(Text, nullable=True, comment="WordPress application password")
    api_key = Column(Text, nullable=True, comment="WordPress Rext-AI API Key (Bearer Token)")

    # Additional configuration (JSON)
    config_json = Column(JSONB, nullable=True, comment="Additional integration configuration and settings")

    # Timestamps
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=True, default=datetime.utcnow, onupdate=datetime.utcnow)
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    workspace = relationship("WorkspaceModel", back_populates="integrations")

    # to_dict() inherited from SerializableMixin
    def to_dict(self):
        return {
            "id": self.id,
            "workspace_id": self.workspace_id,
            "integration_type": self.integration_type,
            "is_active": self.is_active,
            "site_url": self.site_url,
            "api_endpoint": self.api_endpoint,
            "username": self.username,
            "app_password": self.app_password,
            "api_key": self.api_key,
            "config_json": self.config_json,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "deleted_at": self.deleted_at,
        }
