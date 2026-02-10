import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Boolean, DateTime, ForeignKey, Text, Index
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from src.api.database.base import Base
from src.api.models.base import SerializableMixin, SoftDeleteMixin


class Notification(Base, SerializableMixin, SoftDeleteMixin):
    """
    Notification model for storing user notifications.
    
    This model stores all notifications sent to users, including:
    - In-app notifications
    - System notifications
    - Workspace notifications
    - Billing notifications
    - Content generation notifications
    - Knowledge base notifications
    
    Features:
    - Read/unread status tracking
    - Notification type categorization
    - Priority levels
    - Rich payload support (JSONB)
    - Soft delete support
    - Expiration support
    """
    __tablename__ = "notifications"

    # ==============================
    # PRIMARY KEY
    # ==============================
    id = Column(
        UUID(as_uuid=True), 
        primary_key=True, 
        default=uuid.uuid4, 
        unique=True, 
        nullable=False
    )

    # ==============================
    # FOREIGN KEYS
    # ==============================
    user_id = Column(
        UUID(as_uuid=True), 
        ForeignKey("users.id", ondelete="CASCADE"), 
        nullable=False,
        index=True
    )
    
    workspace_id = Column(
        UUID(as_uuid=True), 
        ForeignKey("workspace.id", ondelete="CASCADE"), 
        nullable=True,
        index=True
    )

    # ==============================
    # NOTIFICATION CONTENT
    # ==============================
    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)
    
    # ==============================
    # NOTIFICATION METADATA
    # ==============================
    type = Column(
        String(50), 
        nullable=False,
        index=True,
        comment="Type of notification: workspace, billing, content, knowledge, system, etc."
    )
    
    category = Column(
        String(50), 
        nullable=True,
        index=True,
        comment="Specific category: ws_invite_received, billing_payment_failed, kb_processing_completed, etc."
    )
    
    priority = Column(
        String(20), 
        default="normal",
        nullable=False,
        comment="Priority level: low, normal, high, urgent"
    )
    
    status = Column(
        String(20), 
        default="new",
        nullable=False,
        index=True,
        comment="Status: new, success, warning, error, info"
    )

    # ==============================
    # NOTIFICATION STATE
    # ==============================
    is_read = Column(Boolean, default=False, nullable=False, index=True)
    read_at = Column(DateTime(timezone=True), nullable=True)
    
    is_archived = Column(Boolean, default=False, nullable=False, index=True)
    archived_at = Column(DateTime(timezone=True), nullable=True)

    # ==============================
    # ADDITIONAL DATA
    # ==============================
    payload = Column(
        JSONB, 
        nullable=True,
        comment="Additional data in JSON format (e.g., workspace_id, content_id, etc.)"
    )
    
    action_url = Column(
        String(500), 
        nullable=True,
        comment="URL to navigate to when notification is clicked"
    )
    
    action_label = Column(
        String(100), 
        nullable=True,
        comment="Label for the action button (e.g., 'View Workspace', 'View Invoice')"
    )

    # ==============================
    # NOTIFICATION DELIVERY
    # ==============================
    sent_via_email = Column(Boolean, default=False, nullable=False)
    sent_via_sse = Column(Boolean, default=False, nullable=False)
    email_sent_at = Column(DateTime(timezone=True), nullable=True)
    sse_sent_at = Column(DateTime(timezone=True), nullable=True)

    # ==============================
    # EXPIRATION
    # ==============================
    expires_at = Column(
        DateTime(timezone=True), 
        nullable=True,
        comment="When this notification should expire and be auto-archived"
    )

    # ==============================
    # TIMESTAMPS
    # ==============================
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False
    )

    # ==============================
    # RELATIONSHIPS
    # ==============================
    user = relationship("Users", back_populates="notifications")
    workspace = relationship("WorkspaceModel", back_populates="notifications")

    # ==============================
    # INDEXES
    # ==============================
    __table_args__ = (
        # Composite index for common queries
        Index('idx_user_read_deleted', 'user_id', 'is_read', 'deleted_at'),
        Index('idx_user_created', 'user_id', 'created_at'),
        Index('idx_user_type_created', 'user_id', 'type', 'created_at'),
        Index('idx_workspace_created', 'workspace_id', 'created_at'),
    )

    def to_dict(self, **kwargs):
        """
        Return only selected fields required by the frontend/UI.
        """
        return {
            "id": self.id,
            "user_id": self.user_id,
            "workspace_id": self.workspace_id,
            "title": self.title,
            "message": self.message,
            "type": self.type,
            "category": self.category,
            "status": self.status,
            "is_read": self.is_read,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    def mark_as_read(self):
        """Mark notification as read."""
        self.is_read = True
        self.read_at = datetime.now(timezone.utc)

    def mark_as_unread(self):
        """Mark notification as unread."""
        self.is_read = False
        self.read_at = None

    def archive(self):
        """Archive notification."""
        self.is_archived = True
        self.archived_at = datetime.now(timezone.utc)

    def unarchive(self):
        """Unarchive notification."""
        self.is_archived = False
        self.archived_at = None
