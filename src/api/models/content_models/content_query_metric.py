import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import DateTime, Float, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.orm import relationship, Mapped, mapped_column

from src.api.database.base import Base
from src.api.models.base import SerializableMixin
from src.api.models.mixins import UUIDPrimaryKeyMixin, TimestampMixin


class ContentQueryMetric(Base, SerializableMixin, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    Per-query Search Console breakdown for a single published URL.

    Unlike ContentPerformanceMetric (a daily page-level time series), this is
    current-state — one row per (publishing_result, query), fully replaced on
    each sync (queries can appear/disappear between syncs, so a stale row
    left behind would be misleading). Powers Module 4 (Opportunity Score):
    which specific query is the biggest lever for this page, not just the
    page's blended average across all queries.
    """

    __tablename__ = "content_query_metrics"
    __table_args__ = (
        UniqueConstraint(
            "publishing_result_id", "query",
            name="uq_content_query_metric_result_query",
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

    query: Mapped[str] = mapped_column(Text, nullable=False)
    clicks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    impressions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ctr: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    position: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    window_days: Mapped[int] = mapped_column(Integer, nullable=False)
    synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    content = relationship("Content")
    publishing_result = relationship("ContentPublishingResult")
