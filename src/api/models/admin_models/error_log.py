"""Error Log model for system monitoring."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PostgresUUID

from src.api.database.base import Base
from src.api.models.base import SerializableMixin


class ErrorLog(Base, SerializableMixin):
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
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )
    request_id = Column(String(100))
    stack_trace = Column(Text)
    error_metadata = Column("metadata", JSONB, default=dict)
    resolved = Column(Boolean, default=False, index=True)
    resolved_at = Column(DateTime, nullable=True)
    resolved_by = Column(
        PostgresUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True
    )

    def to_dict(self, **kwargs):
        """Serialize with 'metadata' key for backward compatibility."""
        data = super().to_dict(**kwargs)
        # Rename error_metadata to metadata for API compatibility
        if 'error_metadata' in data:
            data['metadata'] = data.pop('error_metadata')
        return data