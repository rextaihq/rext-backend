import uuid
from datetime import datetime
from typing import Any, Dict, Optional
from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship, Mapped, mapped_column

from src.api.database.base import Base
from src.api.models.base import SerializableMixin
from src.api.models.mixins import UUIDPrimaryKeyMixin, TimestampMixin


class ContentIndexStatus(Base, SerializableMixin, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    Current Search Console index status for a single published URL.

    Unlike ContentPerformanceMetric (a daily time series), this is
    current-state: one row per publishing_result_id, upserted each time the
    URL Inspection API is called (see SearchConsoleInspectionService).
    """

    __tablename__ = "content_index_status"

    content_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("content.id", ondelete="CASCADE"), nullable=False, index=True
    )
    publishing_result_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("content_publishing_results.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False, index=True
    )

    verdict: Mapped[Optional[str]] = mapped_column(
        String(30), nullable=True, index=True,
        comment="PASS, NEUTRAL, FAIL, or VERDICT_UNSPECIFIED",
    )
    coverage_state: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    robots_txt_state: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    indexing_state: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    page_fetch_state: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    last_crawl_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    inspected_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    raw_response: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)

    content = relationship("Content")
    publishing_result = relationship("ContentPublishingResult")
