"""Error Log model for system monitoring."""

from enum import Enum
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import Boolean, Column, DateTime, Enum as SAEnum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PostgresUUID

from src.api.database.base import Base
from src.api.models.base import SerializableMixin


class ErrorLogSeverity(str, Enum):
    """Constrained enum for error log severity values."""

    ERROR = "error"
    WARNING = "warning"
    CRITICAL = "critical"


class ErrorLog(Base, SerializableMixin):
    """
    Model for application error logs.

    Used for tracking and monitoring system errors, warnings, and critical issues.
    """

    __tablename__ = "error_logs"

    id = Column(PostgresUUID(as_uuid=True), primary_key=True, default=uuid4)
    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    severity = Column(
        SAEnum(
            ErrorLogSeverity,
            name="error_log_severity",
            native_enum=False,
            validate_strings=True,
            create_constraint=True,
            # SQLAlchemy stores the enum NAME by default ("WARNING"), but the
            # CHECK constraint was generated from the VALUES ("warning"), so
            # every insert violated it. The failure was swallowed by the
            # best-effort try/except around error logging, which is why the
            # table was empty while errors were plainly occurring.
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        index=True,
    )
    message = Column(Text, nullable=False)
    source = Column(String(255))  # file:line
    user_id = Column(
        PostgresUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )
    request_id = Column(String(100))
    stack_trace = Column(Text)
    error_metadata = Column("metadata", JSONB, default=dict)
    resolved = Column(Boolean, default=False, index=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    resolved_by = Column(
        PostgresUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )

    def to_dict(self, include_stack_trace: bool = False, **kwargs):
        """Serialize ErrorLog with stack traces excluded by default."""
        exclude = list(kwargs.pop("exclude", []))
        if not include_stack_trace and "stack_trace" not in exclude:
            exclude.append("stack_trace")

        data = super().to_dict(exclude=exclude, **kwargs)
        # Rename error_metadata to metadata for API compatibility
        if 'error_metadata' in data:
            data['metadata'] = data.pop('error_metadata')
        # Serialize enum value to plain string
        if 'severity' in data and isinstance(data['severity'], ErrorLogSeverity):
            data['severity'] = data['severity'].value
        return data