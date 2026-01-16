from sqlalchemy import Column, String, Text, Boolean, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from src.api.database.base import Base
from src.api.models.base import SerializableMixin
from datetime import datetime
import uuid


class WorkspaceIntegration(Base, SerializableMixin):
    """
    Workspace Integration Model
    
    Stores third-party integration credentials for workspaces.
    Currently supports WordPress and Shopify (future).
    """
    __tablename__ = "workspace_integrations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=True, nullable=False)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False, index=True)
    integration_type = Column(String(50), nullable=False, index=True)  # 'wordpress', 'shopify'
    is_active = Column(Boolean, default=True, nullable=False)

    # WordPress specific fields
    site_url = Column(String(500), nullable=True, comment="WordPress site URL")
    username = Column(String(255), nullable=True, comment="WordPress username")
    app_password = Column(Text, nullable=True, comment="WordPress application password")

    # Shopify specific fields (for future use)
    shop_domain = Column(String(500), nullable=True, comment="Shopify shop domain")
    access_token = Column(Text, nullable=True, comment="Shopify access token")

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
            "username": self.username,
            "app_password": self.app_password,
            "shop_domain": self.shop_domain,
            "access_token": self.access_token,
            "config_json": self.config_json,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "deleted_at": self.deleted_at,
        }
