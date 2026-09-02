"""ApiUsageHourly Model — durable per-endpoint API usage rollup."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import BigInteger, Column, DateTime, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID

from src.api.database.base import Base
from src.api.models.base import SerializableMixin


class ApiUsageHourly(Base, SerializableMixin):
    """
    One row per (hour, endpoint, method).

    Live counting happens in Redis so the request path stays fast, but Redis
    keys are short-lived. A scheduled task drains completed minute buckets into
    this table, which is what makes "last 7 days" and "last 30 days" answerable
    at all — previously those periods read the same ~1h of Redis data and could
    report a *smaller* total for a wider window.
    """
    __tablename__ = "api_usage_hourly"
    __table_args__ = (
        UniqueConstraint(
            "hour_bucket", "endpoint", "method",
            name="uq_api_usage_hour_endpoint_method",
        ),
        Index("ix_api_usage_hourly_bucket", "hour_bucket"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Start of the UTC hour this row aggregates.
    hour_bucket = Column(DateTime(timezone=True), nullable=False, index=True)
    # Route template (e.g. "/api/v1/workspaces/{workspace_id}"), never the raw
    # path — raw paths would explode into one row per id.
    endpoint = Column(String(255), nullable=False)
    method = Column(String(10), nullable=False, default="GET")
    request_count = Column(Integer, nullable=False, default=0)
    error_count = Column(Integer, nullable=False, default=0)
    # Summed so an average can be derived without storing every sample.
    total_duration_ms = Column(BigInteger, nullable=False, default=0)
    created_at = Column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = Column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    def __repr__(self):
        return (f"<ApiUsageHourly({self.hour_bucket} {self.method} {self.endpoint} "
                f"n={self.request_count})>")
