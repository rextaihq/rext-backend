"""Error Log model for system monitoring."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PostgresUUID

from src.api.database.base import Base


class ErrorLog(Base):
    """
    Model for application error logs.

    Used for tracking and monitoring system errors, warnings, and critical issues.
    """

    __tablename__ = "error_logs"

    id = Column(PostgresUUID(as_uuid=True), primary_key=True, default=uuid4)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    severity = Column(String(20), nullable=False, index=True)  # error, warning, critical
    message = Column(Text, nullable=False)
    source = Column(String(255))  # file:line
    user_id = Column(
        PostgresUUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=True
    )
    request_id = Column(String(100))
    stack_trace = Column(Text)
    error_metadata = Column("metadata", JSONB, default=dict)
    resolved = Column(Boolean, default=False, index=True)
    resolved_at = Column(DateTime, nullable=True)
    resolved_by = Column(
        PostgresUUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=True
    )

    def to_dict(self) -> dict:
        """Convert error log to dictionary."""
        return {
            "id": str(self.id),
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "severity": self.severity,
            "message": self.message,
            "source": self.source,
            "user_id": str(self.user_id) if self.user_id else None,
            "request_id": self.request_id,
            "stack_trace": self.stack_trace,
            "metadata": self.error_metadata,
            "resolved": self.resolved,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "resolved_by": str(self.resolved_by) if self.resolved_by else None
        }
