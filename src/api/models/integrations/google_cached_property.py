"""
Local cache of the Google-side properties a workspace's connected account can
access — Search Console properties and GA4 properties, synced from Google on
OAuth completion and TTL-refreshed when selection screens open. Serving these
from the DB keeps the UI fast and resilient to Google API hiccups; the cache
is the source the user picks from, never the source of truth for access
(mappings are still validated against Google on save).

GSC and GA4 are cached in separate tables because Google exposes them as two
unrelated lists — pairing one with the other is the user's mapping decision
(GoogleSiteMapping), not data Google provides.
"""

from datetime import datetime
import uuid
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.api.database.base import Base
from src.api.models.base import SerializableMixin
from src.api.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class GoogleGscProperty(Base, SerializableMixin, UUIDPrimaryKeyMixin, TimestampMixin):
    """One verified Search Console property visible to the connected account."""

    __tablename__ = "google_gsc_properties"
    __table_args__ = (
        UniqueConstraint("workspace_id", "site_url", name="uq_google_gsc_property_ws_url"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False, index=True
    )
    site_url: Mapped[str] = mapped_column(
        String(500), nullable=False, comment="Search Console property (siteUrl)"
    )
    permission_level: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    synced_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class GoogleGa4Property(Base, SerializableMixin, UUIDPrimaryKeyMixin, TimestampMixin):
    """One GA4 property visible to the connected account (Admin API)."""

    __tablename__ = "google_ga4_properties"
    __table_args__ = (
        UniqueConstraint("workspace_id", "property_id", name="uq_google_ga4_property_ws_id"),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False, index=True
    )
    property_id: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="GA4 property, e.g. properties/123456789"
    )
    display_name: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    account_display_name: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    synced_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
