"""ApiUsageHourly - durable hourly totals for API request volume."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import BigInteger, Column, DateTime, Integer
from sqlalchemy.dialects.postgresql import UUID

from src.api.database.base import Base
from src.api.models.base import SerializableMixin


class ApiUsageHourly(Base, SerializableMixin):
    """
    One row per UTC hour: how many API requests happened in it.

    Live counting stays in Redis -- it runs on every request, so it has to be
    fast -- but Redis keys expire after an hour. A scheduled task copies each
    completed minute in here before it disappears, so nothing that already
    worked is removed; the history simply stops evaporating.

    Without this, "7 days" and "30 days" both summed whatever ~1h of Redis keys
    had not yet expired, and a wider period could report a SMALLER total.
    """

    __tablename__ = "api_usage_hourly"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Start of the UTC hour. Unique: the rollup upserts onto it.
    hour_bucket = Column(DateTime(timezone=True), nullable=False, unique=True, index=True)
    request_count = Column(Integer, nullable=False, default=0)
    error_count = Column(Integer, nullable=False, default=0)
    # Summed, so an average is derivable without storing every sample.
    total_duration_ms = Column(BigInteger, nullable=False, default=0)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    def __repr__(self):
        return f"<ApiUsageHourly({self.hour_bucket} n={self.request_count})>"


class ApiUsageRollupState(Base, SerializableMixin):
    """
    Single-row watermark marking how far Redis->Postgres settlement has run.

    Exact-once accounting depends on this, not on whether a Redis key still
    exists. Inferring "already settled" from key absence is unsafe: a failed
    DELETE, or a crash between commit and delete, leaves a minute present in
    both stores and it gets counted twice, permanently.

    Updated in the same transaction as the hourly upserts, so the boundary
    moves atomically with the data it describes.
    """

    __tablename__ = "api_usage_rollup_state"

    id = Column(Integer, primary_key=True, default=1)
    # Every minute bucket at or before this instant is already in
    # api_usage_hourly. Readers must count Redis only *after* it.
    settled_through = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    def __repr__(self):
        return f"<ApiUsageRollupState(settled_through={self.settled_through})>"
