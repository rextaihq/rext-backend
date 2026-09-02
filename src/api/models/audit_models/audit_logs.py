"""Audit log model for tracking sensitive operations."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID

from src.api.database.base import Base
from src.api.models.base import SerializableMixin


class AuditLog(Base, SerializableMixin):
    """Audit log model for tracking sensitive operations."""

    __tablename__ = "audit_logs"

    id = Column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=True, nullable=False
    )

    # Who performed the action
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    full_name = Column(String(200))  # Denormalized for historical record
    user_email = Column(String(255))  # Denormalized for historical record

    # What action was performed
    action = Column(
        String(100), nullable=False
    )  # e.g., "user.create", "role.assign", "permission.revoke"
    resource_type = Column(String(50), nullable=False)  # e.g., "user", "role", "workspace"
    resource_id = Column(String(255))  # ID of the affected resource

    # Where the action was performed
    workspace_id = Column(
        UUID(as_uuid=True), ForeignKey("workspace.id", ondelete="SET NULL"), nullable=True
    )

    # Request details
    ip_address = Column(INET)
    user_agent = Column(Text)
    request_id = Column(String(255))  # For correlating with application logs

    # Change details
    old_values = Column(JSONB)  # Previous state
    new_values = Column(JSONB)  # New state
    audit_metadata = Column(JSONB)  # Additional context

    # Status
    status = Column(String(20), default="success")  # success, failed, partial
    error_message = Column(Text)  # If status is failed

    # Timestamp
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )

    __table_args__ = (
        Index("idx_audit_logs_user_id", "user_id"),
        Index("idx_audit_logs_action", "action"),
        Index("idx_audit_logs_resource_type", "resource_type"),
        Index("idx_audit_logs_resource_id", "resource_id"),
        Index("idx_audit_logs_workspace_id", "workspace_id"),
        Index("idx_audit_logs_created_at", "created_at"),
    )

    # to_dict() inherited from SerializableMixin
