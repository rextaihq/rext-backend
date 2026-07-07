"""
Workspace Google Connection Model

Stores workspace-level Google integration configuration.
Links a workspace to selected GSC site and GA4 property.
"""

import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import String, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship, Mapped, mapped_column

from src.api.database.base import Base
from src.api.models.base import SerializableMixin
from src.api.models.mixins import UUIDPrimaryKeyMixin, TimestampMixin


class WorkspaceGoogleConnection(
    Base, SerializableMixin, UUIDPrimaryKeyMixin, TimestampMixin
):
    """
    Workspace-level Google integration state.
    Stores selected GSC site and GA4 property for a workspace.
    
    Each workspace can have exactly one Google connection (enforced by unique constraint).
    The connection links to an OAuthAccount that provides the access tokens.
    """

    __tablename__ = "workspace_google_connections"
    __table_args__ = (
        UniqueConstraint("workspace_id", name="uq_workspace_google_connection"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspace.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        unique=True,
    )

    oauth_account_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("oauth_accounts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # GSC configuration
    gsc_site_url: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
        comment="Selected GSC site URL (e.g., https://example.com/)"
    )

    # GA4 configuration
    ga4_property_id: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="Selected GA4 property ID (e.g., properties/123456789)"
    )

    # Sync tracking
    last_synced_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Last successful incremental sync timestamp"
    )

    last_backfill_completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Timestamp when 16-month backfill completed"
    )

    # Relationships
    workspace = relationship("WorkspaceModel", back_populates="google_connection")
    oauth_account = relationship("OAuthAccount")
