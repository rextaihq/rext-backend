import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.api.database.base import Base
from src.api.models.base import SerializableMixin
from src.api.models.mixins import UUIDPrimaryKeyMixin


# -------------------------
# Workspace Members
# -------------------------
class WorkspaceMembers(Base, SerializableMixin, UUIDPrimaryKeyMixin):
    __tablename__ = "workspace_members"

    # id provided by mixin
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspace.id", ondelete="CASCADE"), nullable=False
    )
    invitation_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("user_invitations.id", ondelete="SET NULL"), nullable=True
    )

    status: Mapped[str] = mapped_column(String(50), default="pending")  # active, inactive, pending
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)

    # Note: We use manual timestamps here instead of TimestampMixin because the
    # field names are joined_at and last_activity_at, not created_at and updated_at.
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    last_activity_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=True,
    )

    __table_args__ = (UniqueConstraint("user_id", "workspace_id", name="uq_user_workspace"),)

    # Relationships
    user = relationship("Users", foreign_keys=[user_id], back_populates="workspace_memberships")
    workspace = relationship(
        "WorkspaceModel", foreign_keys=[workspace_id], back_populates="members"
    )
    invitation = relationship(
        "UserInvitations", foreign_keys=[invitation_id], back_populates="workspace_members"
    )
