import uuid
from datetime import date as date_
from typing import Any, Dict, Optional

from sqlalchemy import Date, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship, Mapped, mapped_column

from src.api.database.base import Base
from src.api.models.base import SerializableMixin
from src.api.models.mixins import UUIDPrimaryKeyMixin, TimestampMixin


class SiteDailyMetric(Base, SerializableMixin, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    Daily Search Console / GA4 metric snapshot for a whole site (property
    level, no page filter) — as opposed to ContentPerformanceMetric, which is
    per published URL. Powers the site-wide dashboard totals; the per-URL
    rows keep powering content inventory / health / opportunity / diagnosis.

    ``site_id`` is the WorkspaceIntegration.id of the WordPress site (same
    key GoogleSiteMapping uses). ``metrics`` is a JSONB payload whose shape
    depends on ``source`` (see ``SearchConsoleService.sync_site_metrics`` /
    ``GoogleAnalyticsService.sync_site_metrics``).
    """

    __tablename__ = "site_daily_metrics"
    __table_args__ = (
        UniqueConstraint(
            "site_id", "source", "metric_date",
            name="uq_site_daily_metric_site_source_date",
        ),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False, index=True
    )
    site_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("integrations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="WorkspaceIntegration.id of the connected WordPress site",
    )

    source: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    metric_date: Mapped[date_] = mapped_column(Date, nullable=False, index=True)
    metrics: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    synced_at: Mapped[Optional[Any]] = mapped_column(DateTime(timezone=True), nullable=True)

    workspace = relationship("WorkspaceModel")
    site = relationship("WorkspaceIntegration")
