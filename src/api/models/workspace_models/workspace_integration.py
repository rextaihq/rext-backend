
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from src.api.database.base import Base
from src.api.models.base import SerializableMixin, SoftDeleteMixin
from datetime import datetime, timezone
import uuid


class WorkspaceIntegration(Base, SerializableMixin, SoftDeleteMixin):
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
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=True, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    workspace = relationship("WorkspaceModel", back_populates="integrations")

    def to_dict(self, **kwargs):
        """
        Serialize integration, excluding sensitive credentials by default.
        """
        if 'exclude' not in kwargs:
            kwargs['exclude'] = ['app_password', 'api_key']
        return super().to_dict(**kwargs)
