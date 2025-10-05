"""Audit log model for tracking sensitive operations."""
import uuid
from datetime import datetime
from sqlalchemy import Column, String, Text, TIMESTAMP, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB, INET
from src.api.database.database import Base


class AuditLog(Base):
    """Audit log model for tracking sensitive operations."""
    __tablename__ = "audit_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=True, nullable=False)

    # Who performed the action
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    username = Column(String(100))  # Denormalized for historical record
    user_email = Column(String(255))  # Denormalized for historical record

    # What action was performed
    action = Column(String(100), nullable=False)  # e.g., "user.create", "role.assign", "permission.revoke"
    resource_type = Column(String(50), nullable=False)  # e.g., "user", "role", "workspace"
    resource_id = Column(String(255))  # ID of the affected resource

    # Where the action was performed
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspace.id", ondelete="SET NULL"), nullable=True)

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
    created_at = Column(TIMESTAMP, default=datetime.utcnow, nullable=False, index=True)

    __table_args__ = (
        Index('idx_audit_logs_user_id', 'user_id'),
        Index('idx_audit_logs_action', 'action'),
        Index('idx_audit_logs_resource_type', 'resource_type'),
        Index('idx_audit_logs_resource_id', 'resource_id'),
        Index('idx_audit_logs_workspace_id', 'workspace_id'),
        Index('idx_audit_logs_created_at', 'created_at'),
    )

    def to_dict(self):
        """Convert model to dictionary."""
        return {
            "id": str(self.id),
            "user_id": str(self.user_id) if self.user_id else None,
            "username": self.username,
            "user_email": self.user_email,
            "action": self.action,
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "workspace_id": str(self.workspace_id) if self.workspace_id else None,
            "ip_address": str(self.ip_address) if self.ip_address else None,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
