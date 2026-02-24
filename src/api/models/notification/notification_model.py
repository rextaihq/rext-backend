import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Boolean, DateTime, ForeignKey, Text, Index, text
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from src.api.database.base import Base
from src.api.models.base import SerializableMixin, SoftDeleteMixin


class Notification(Base, SerializableMixin, SoftDeleteMixin):
    """
    Notification model for storing user notifications.
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
        comment="Type of notification"
    )

    category = Column(
        String(50),
        nullable=True,
        index=True,
        comment="Specific notification category"
    )

    priority = Column(
        String(20),
        default="normal",
        nullable=False
    )

    status = Column(
        String(20),
        default="new",
        nullable=False,
        index=True
    )

    # ==============================
    # NOTIFICATION STATE
    # ==============================
    is_read = Column(Boolean, default=False, nullable=False, index=True)
    read_at = Column(DateTime(timezone=True), nullable=True)

    is_archived = Column(Boolean, default=False, nullable=False, index=True)
    archived_at = Column(DateTime(timezone=True), nullable=True)

    # is_deleted and deleted_at are provided by SoftDeleteMixin

    # ==============================
    # ADDITIONAL DATA
    # ==============================
    payload = Column(JSONB, nullable=True)
    action_url = Column(String(500), nullable=True)
    action_label = Column(String(100), nullable=True)

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
    expires_at = Column(DateTime(timezone=True), nullable=True)

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
        # Primary listing query: user's active (non-deleted, non-archived) notifications
        # Covers: get_notifications base query, clear_notifications, get_notification_by_id
        Index(
            'idx_notif_user_active_created',
            'user_id', 'created_at',
            postgresql_where=text("is_deleted = false AND is_archived = false"),
        ),
        # Unread count + unread filter (most frequent — badge counter polling)
        # Covers: get_unread_count, get_notifications(unread_only=True), mark_notifications_as_read
        Index(
            'idx_notif_user_unread',
            'user_id',
            postgresql_where=text("is_deleted = false AND is_archived = false AND is_read = false"),
        ),
        # Type filter: get_notifications with ?type= parameter
        Index(
            'idx_notif_user_type_created',
            'user_id', 'type', 'created_at',
            postgresql_where=text("is_deleted = false AND is_archived = false"),
        ),
        # Category filter: get_notifications with ?category= parameter
        Index(
            'idx_notif_user_category_created',
            'user_id', 'category', 'created_at',
            postgresql_where=text("is_deleted = false AND is_archived = false"),
        ),
        # Workspace filter: get_notifications with ?workspace_id= parameter
        Index(
            'idx_notif_user_workspace_created',
            'user_id', 'workspace_id', 'created_at',
            postgresql_where=text("is_deleted = false AND is_archived = false"),
        ),
        # Mark-as-read queries filter on is_read; keep a non-partial index for that path
        Index('idx_user_read_deleted', 'user_id', 'is_read', 'is_deleted'),
    )

    # ✅ FIXED to_dict (TASK-054 compliant)
    def to_dict(self, **kwargs):
        """Return only fields required by the frontend/UI."""
        if 'exclude' not in kwargs:
            kwargs['exclude'] = [
                'is_archived', 'archived_at',
                'is_deleted', 'deleted_at',
                'payload', 'action_url', 'action_label',
                'sent_via_email', 'sent_via_sse',
                'email_sent_at', 'sse_sent_at',
                'expires_at', 'read_at', 'priority',
            ]
        return super().to_dict(**kwargs)

    # ==============================
    # HELPERS
    # ==============================
    def mark_as_read(self):
        self.is_read = True
        self.read_at = datetime.now(timezone.utc)

    def mark_as_unread(self):
        self.is_read = False
        self.read_at = None

    def archive(self):
        self.is_archived = True
        self.archived_at = datetime.now(timezone.utc)

    def unarchive(self):
        self.is_archived = False
        self.archived_at = None

