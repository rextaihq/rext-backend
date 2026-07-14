from datetime import datetime, timezone
import uuid
from typing import Optional, Any, Dict
from sqlalchemy import String, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship, Mapped, mapped_column

from src.api.database.base import Base
from src.api.models.base import SerializableMixin
from src.api.models.mixins import UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin
from src.utils.encryption import EncryptedText


class GoogleIntegration(
    Base, SerializableMixin, UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin
):
    """
    Workspace-scoped Google OAuth 2.0 connection.

    Stores the shared OAuth tokens used to call both the Search Console API
    and the GA4 Data API on behalf of a workspace. Per-WordPress-site GSC/GA4
    property selection lives in ``GoogleSiteMapping``, not here.
    """

    __tablename__ = "google_integrations"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False, index=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    google_account_email: Mapped[Optional[str]] = mapped_column(
        String(255), nullable=True, comment="Email of the connected Google account"
    )
    access_token: Mapped[Optional[str]] = mapped_column(
        EncryptedText, nullable=True, comment="OAuth access token (encrypted)"
    )
    refresh_token: Mapped[Optional[str]] = mapped_column(
        EncryptedText, nullable=True, comment="OAuth refresh token (encrypted)"
    )
    token_expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    scopes: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True, comment="Space-separated OAuth scopes granted"
    )
    connected_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    last_refreshed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    workspace = relationship("WorkspaceModel")

    def to_dict(self, include_credentials: bool = False, **kwargs) -> dict:
        """Convert model to dictionary for JSON serialization. Tokens hidden unless requested."""
        exclude = kwargs.get("exclude", []) or []
        if isinstance(exclude, str):
            exclude = [exclude]
        else:
            exclude = list(exclude)

        if not include_credentials:
            exclude.extend(["access_token", "refresh_token"])

        kwargs["exclude"] = exclude

        data = super().to_dict(**kwargs)
        data["has_refresh_token"] = bool(self.refresh_token)
        return data
