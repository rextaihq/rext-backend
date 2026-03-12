from datetime import datetime, timezone
import uuid
from typing import Optional, Any, Dict, List
from sqlalchemy import String, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship, Mapped, mapped_column
from src.api.database.base import Base
from src.api.models.base import SerializableMixin
from src.api.models.mixins import UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin
from src.utils.encryption import EncryptedText


class WorkspaceIntegration(Base, SerializableMixin, UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin):
    """
    Connected Site Model

    Stores WordPress integration credentials for workspaces.
    Sensitive fields (app_password, api_key) are encrypted at rest.
    """
    __tablename__ = "integrations"

    # id, created_at, updated_at, deleted_at provided by mixins
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False, index=True)
    integration_type: Mapped[str] = mapped_column(String(50), nullable=False, default="wordpress", index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # WordPress specific fields
    site_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True, comment="WordPress site URL")
    api_endpoint: Mapped[Optional[str]] = mapped_column(String(500), nullable=True, comment="Rext-AI Plugin Base Endpoint")
    username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, comment="WordPress username")
    app_password: Mapped[Optional[str]] = mapped_column(EncryptedText, nullable=True, comment="WordPress application password (encrypted)")
    api_key: Mapped[Optional[str]] = mapped_column(EncryptedText, nullable=True, comment="WordPress Rext-AI API Key (encrypted)")

    # Additional configuration (JSON)
    config_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True, comment="Additional integration configuration and settings")

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
        exclude = kwargs.get('exclude', []) or []
        if isinstance(exclude, str):
            exclude = [exclude]
        else:
            exclude = list(exclude)

        if not include_credentials:
            exclude.extend(['app_password', 'api_key'])

        kwargs['exclude'] = exclude

        # Use parent's to_dict which handles UUID/datetime conversion
        data = super().to_dict(**kwargs)

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
