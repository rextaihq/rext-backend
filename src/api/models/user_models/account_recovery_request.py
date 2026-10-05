"""
Account Recovery Request model.

Backs the "Account Recovery" tab in admin User Management. A deleted or
deactivated user files a request from the recovery page; it lands here as
``pending`` and an authorized admin approves it (which restores the account) or
rejects it. The requester is emailed the outcome either way.

This is the admin-reviewed path. The time-limited self-service recovery link
issued when an admin soft-deletes an account (see
routes/users/management.delete_user) still works independently.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from src.api.database.base import Base
from src.api.models.base import SerializableMixin


class AccountRecoveryRequest(Base, SerializableMixin):
    """
    A user's request to recover a deleted/deactivated account, pending admin review.

    Status values (see enums.RecoveryRequestStatus):
    - pending:  awaiting admin review
    - approved: admin approved; the account was restored
    - rejected: admin declined the request
    """

    __tablename__ = "account_recovery_requests"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
    )

    # The account being recovered. Kept nullable + SET NULL so a permanent
    # purge of the user does not wipe the review history.
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Captured at request time so the row is still meaningful if the user is gone.
    email = Column(String(255), nullable=False, index=True)

    # pending | approved | rejected
    status = Column(
        String(20),
        default="pending",
        nullable=False,
        index=True,
    )

    # Free-text note the requester can add, and the admin's review note.
    request_note = Column(Text, nullable=True)
    review_note = Column(Text, nullable=True)

    requested_ip = Column(String(64), nullable=True)
    requested_user_agent = Column(String(512), nullable=True)

    reviewed_by_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    reviewed_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("Users", foreign_keys=[user_id])
    reviewed_by = relationship("Users", foreign_keys=[reviewed_by_user_id])

    __table_args__ = (
        # At most one open request per email — a user spamming the recovery
        # form should not flood the admin queue.
        Index(
            "uq_account_recovery_email_pending",
            "email",
            unique=True,
            postgresql_where=text("status = 'pending'"),
        ),
    )

    def is_pending(self) -> bool:
        return self.status == "pending"

    def __repr__(self):
        return f"<AccountRecoveryRequest(id={self.id}, email={self.email}, status={self.status})>"
