import enum
import uuid
from datetime import date as date_
from typing import Any, Dict, Optional
from sqlalchemy import Date, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship, Mapped, mapped_column

from src.api.database.base import Base
from src.api.models.base import SerializableMixin
from src.api.models.mixins import UUIDPrimaryKeyMixin, TimestampMixin


class PerformanceMetricSource(str, enum.Enum):
    SEARCH_CONSOLE = "search_console"
    ANALYTICS = "analytics"


class ContentPerformanceMetric(Base, SerializableMixin, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    Daily Search Console / GA4 metric snapshot for a single published URL.

    Keyed off ``ContentPublishingResult`` (not ``Content`` directly) because a
    piece of content can be published to more than one site, and GSC/GA4 data
    is inherently per-URL. ``metrics`` is a JSONB payload whose shape depends
    on ``source`` (see ``SearchConsoleService`` / ``GoogleAnalyticsService``).
    """

    __tablename__ = "content_performance_metrics"
    __table_args__ = (
        UniqueConstraint(
            "publishing_result_id", "source", "metric_date",
            name="uq_content_performance_metric_result_source_date",
        ),
    )

    content_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("content.id", ondelete="CASCADE"), nullable=False, index=True
    )
    publishing_result_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("content_publishing_results.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False, index=True
    )

    source: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    metric_date: Mapped[date_] = mapped_column(Date, nullable=False, index=True)
    metrics: Mapped[Dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    synced_at: Mapped[Optional[Any]] = mapped_column(DateTime(timezone=True), nullable=True)

    content = relationship("Content")
    publishing_result = relationship("ContentPublishingResult")
