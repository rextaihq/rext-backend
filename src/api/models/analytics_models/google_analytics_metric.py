"""
Google Analytics Metric Model

Stores daily analytics metrics for published articles from GSC and GA4.
Supports flexible JSONB schema for different metric types.
"""

import uuid
from datetime import date
from typing import Optional, Dict, Any
from sqlalchemy import String, Date, ForeignKey, Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship, Mapped, mapped_column

from src.api.database.base import Base
from src.api.models.base import SerializableMixin
from src.api.models.mixins import UUIDPrimaryKeyMixin, TimestampMixin


class GoogleAnalyticsMetric(
    Base, SerializableMixin, UUIDPrimaryKeyMixin, TimestampMixin
):
    """
    Daily analytics metrics for published articles.
    Stores both GSC and GA4 data with flexible JSONB schema.
    
    GSC metrics (source='gsc') store one row per (article, date, query keyword).
    GA4 metrics (source='ga4') store one row per (article, date).
    """

    __tablename__ = "google_analytics_metrics"
    __table_args__ = (
        Index(
            "ix_ga_metrics_workspace_url_date_source",
            "workspace_id", "article_external_url", "date", "source"
        ),
        UniqueConstraint(
            "workspace_id", "article_external_url", "date", "source", "query_keyword",
            name="uq_ga_metric_unique"
        ),
    )

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspace.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Article identification (using external_url from ContentPublishingResult)
    article_external_url: Mapped[str] = mapped_column(
        String(1000),
        nullable=False,
        comment="Normalized external URL from ContentPublishingResult"
    )

    # Temporal dimension
    date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        index=True,
        comment="Date for which metrics are recorded"
    )

    # Source: 'gsc' or 'ga4'
    source: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        comment="Data source: 'gsc' or 'ga4'"
    )

    # Metric storage (flexible JSONB for extensibility)
    # GSC: {clicks, impressions, ctr, position}
    # GA4: {sessions, active_users, engagement_rate, conversions}
    metrics: Mapped[Dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        comment="Metrics object: {clicks, impressions, ctr, position} for GSC or {sessions, active_users, engagement_rate, conversions} for GA4"
    )

    # GSC-specific: keyword/query dimension
    query_keyword: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
        comment="Search query keyword (GSC only, NULL for GA4)"
    )

    # Relationships
    workspace = relationship("WorkspaceModel")
