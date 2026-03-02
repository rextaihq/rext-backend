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

    Lifecycle states:
    - is_read / read_at: whether the user has seen the notification
    - is_deleted / deleted_at: soft delete via SoftDeleteMixin (cleared notifications)

    Note: Archive functionality was removed as it had no consumers.
    Use soft delete (clear) for removing notifications from the user's view.
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

    # Note: is_deleted and deleted_at are provided by SoftDeleteMixin.
    # Do NOT redeclare them here — the mixin's hybrid property handles both
    # Python-side and SQL-side is_deleted checks via deleted_at.

    # ==============================
    # ADDITIONAL DATA
    # ==============================
    payload = Column(JSONB, nullable=True)
    action_url = Column(Text, nullable=True)
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
        Index('idx_user_read_deleted', 'user_id', 'is_read', 'deleted_at'),
        Index('idx_user_created', 'user_id', 'created_at'),
        Index('idx_user_type_created', 'user_id', 'type', 'created_at'),
        Index('idx_workspace_created', 'workspace_id', 'created_at'),
        # Deduplication index — supports the time-windowed duplicate check
        Index('idx_dedup_user_category_workspace', 'user_id', 'category', 'workspace_id', 'created_at'),
    )

    def to_dict(self, **kwargs):
        """Return notification data for the frontend/UI.

        Exposes all user-facing fields including priority, action buttons,
        payload, and read timestamp. Excludes internal state tracking
        (soft delete, archive) and delivery channel metadata.
        """
        if 'exclude' not in kwargs:
            kwargs['exclude'] = [
                # Internal state — not needed by frontend
                'is_archived', 'archived_at',
                'is_deleted', 'deleted_at',
                # Delivery channel tracking — internal metadata
                'sent_via_email', 'sent_via_sse',
                'email_sent_at', 'sse_sent_at',
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

