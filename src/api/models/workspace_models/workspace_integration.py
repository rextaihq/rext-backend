from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from src.api.database.base import Base
from src.api.models.base import SerializableMixin, SoftDeleteMixin
from src.utils.encryption import EncryptedText
from datetime import datetime, timezone
import uuid


class WorkspaceIntegration(Base, SerializableMixin, SoftDeleteMixin):
    """
    Connected Site Model

    Stores WordPress integration credentials for workspaces.
    Sensitive fields (app_password, api_key) are encrypted at rest.
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
    app_password = Column(EncryptedText, nullable=True, comment="WordPress application password (encrypted)")
    api_key = Column(EncryptedText, nullable=True, comment="WordPress Rext-AI API Key (encrypted)")

    # Additional configuration (JSON)
    config_json = Column(JSONB, nullable=True, comment="Additional integration configuration and settings")

    # Timestamps
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=True, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    workspace = relationship("WorkspaceModel", back_populates="integrations")

    def to_dict(self, include_credentials: bool = False, **kwargs) -> dict:
        """
        Convert model to dictionary for JSON serialization.

        By default, sensitive credentials (app_password, api_key) are excluded.
        Only include credentials when explicitly needed (e.g., admin credential management).

        Args:
            include_credentials: If True, include app_password and api_key. Default: False.
            **kwargs: Additional arguments passed to SerializableMixin.to_dict()

        Returns:
            Dictionary representation with UUIDs and datetimes converted to strings.
        """
        # Build exclude list - always exclude credentials unless explicitly requested
        exclude = kwargs.pop('exclude', []) or []
        if not include_credentials:
            exclude.extend(['app_password', 'api_key'])

        # Use parent's to_dict which handles UUID/datetime conversion
        data = super().to_dict(exclude=exclude, **kwargs)

        # Add status flags for UI (indicates if secrets are present without exposing them)
        data["has_app_password"] = self.app_password is not None and len(self.app_password) > 0
        data["has_api_key"] = self.api_key is not None and len(self.api_key) > 0

        return data

    def to_dict_with_credentials(self, **kwargs) -> dict:
        """
        Return full model data including sensitive credentials.

        WARNING: Only use this in admin/credential management contexts where
        the requester has explicit authorization to view credentials.
        """
        return self.to_dict(include_credentials=True, **kwargs)
