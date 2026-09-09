import uuid
from typing import Any, Dict, Optional

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.api.database.base import Base
from src.api.models.base import SerializableMixin
from src.api.models.mixins import SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin
from src.utils.encryption import EncryptedText


class WorkspaceIntegration(
    Base, SerializableMixin, UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin
):
    """
    Connected Site Model

    Stores workspace-scoped integration credentials and settings.
    Sensitive fields (app_password, api_key) are encrypted at rest.
    """

    __tablename__ = "integrations"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False, index=True
    )
    integration_type: Mapped[str] = mapped_column(
        String(50), nullable=False, default="wordpress", index=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    site_url: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True, comment="Integration site URL"
    )
    api_endpoint: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True, comment="Provider-specific API endpoint"
    )
    username: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True, comment="Provider username"
    )
    app_password: Mapped[Optional[str]] = mapped_column(
        EncryptedText,
        nullable=True,
        comment="Provider application password (encrypted)",
    )
    api_key: Mapped[Optional[str]] = mapped_column(
        EncryptedText, nullable=True, comment="Provider API key or token (encrypted)"
    )

    config_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=True,
        comment="Additional integration configuration and settings",
    )

    workspace = relationship("WorkspaceModel", back_populates="integrations")

    def to_dict(self, include_credentials: bool = False, **kwargs) -> dict:
        """
        Convert model to dictionary for JSON serialization.

        Credentials stay hidden unless explicitly requested.
        """
        exclude = kwargs.get("exclude", []) or []
        if isinstance(exclude, str):
            exclude = [exclude]
        else:
            exclude = list(exclude)

        if not include_credentials:
            exclude.extend(["app_password", "api_key"])

        kwargs["exclude"] = exclude

        data = super().to_dict(**kwargs)
        data["has_app_password"] = self.app_password is not None and len(self.app_password) > 0
        data["has_api_key"] = self.api_key is not None and len(self.api_key) > 0

        return data

    def to_dict_with_credentials(self, **kwargs) -> dict:
        """Return full model data including sensitive credentials."""
        return self.to_dict(include_credentials=True, **kwargs)
