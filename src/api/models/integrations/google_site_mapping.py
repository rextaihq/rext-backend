from datetime import datetime
import uuid
from typing import Optional
from sqlalchemy import String, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship, Mapped, mapped_column

from src.api.database.base import Base
from src.api.models.base import SerializableMixin
from src.api.models.mixins import UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin


class GoogleSiteMapping(
    Base, SerializableMixin, UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin
):
    """
    Maps a single connected WordPress site (``WorkspaceIntegration``) to the
    Google Search Console property and GA4 property that report on it.

    One row per WordPress site — a workspace with multiple WordPress sites
    can map each to a different GSC/GA4 property while sharing one
    ``GoogleIntegration`` OAuth connection.
    """

    __tablename__ = "google_site_mappings"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False, index=True
    )
    site_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("integrations.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
        comment="WorkspaceIntegration.id of the connected WordPress site",
    )

    gsc_site_url: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True, comment="Search Console property (siteUrl)"
    )
    ga4_property_id: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True, comment="GA4 property, e.g. properties/123456789"
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_synced_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    workspace = relationship("WorkspaceModel")
    site = relationship("WorkspaceIntegration")
