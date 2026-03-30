"""
Platform Admin Invitations Model

This model manages invitations for platform-level administrators (super admins).
Unlike workspace invitations, these invitations grant platform-wide administrative access.

Key Differences from UserInvitations:
- Platform-level access (not workspace-scoped)
- Only super_admin can create these invitations
- Grants admin role upon acceptance
- Email must be unique (one admin invitation per email)
- More restrictive and security-focused

Related Models:
- Users: The invited user (after acceptance)
- Role: The admin role being assigned
"""

import uuid
from sqlalchemy import Column, String, DateTime, ForeignKey, Text, Index, text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from datetime import datetime, timezone

from src.api.database.base import Base
from src.api.models.base import SerializableMixin


class PlatformAdminInvitations(Base, SerializableMixin):
    """
    Platform admin invitations table.

    Manages invitations for platform-level administrators.
    Separate from workspace invitations for security and clarity.

    Status Values:
    - pending: Invitation sent, awaiting acceptance
    - accepted: Invitation accepted, user is now admin
    - revoked: Invitation cancelled by super admin
    - expired: Invitation passed expiry date
    - declined: Invitee explicitly declined

    Security Notes:
    - Token must be long, random, and single-use
    - Email verification should be required for admin access
    - Audit all admin invitation actions
    - Rate limit invitation creation
    """
    __tablename__ = "platform_admin_invitations"

    # Primary Key
    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        unique=True,
        nullable=False,
        comment="Unique identifier for the admin invitation"
    )

    # Invitation Details
    email = Column(
        String(255),
        nullable=False,
        index=True,
        comment="Email address of the invited admin"
    )

    invitation_token = Column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
        comment="Secure token for invitation acceptance"
    )

    # Status & Role
    status = Column(
        String(50),
        default="pending",
        nullable=False,
        index=True,
        comment="Invitation status: pending, accepted, revoked, expired, declined"
    )

    admin_role = Column(
        String(50),
        nullable=False,
        comment="Admin role to assign: super_admin, support_admin, etc."
    )

    # Optional: Additional permissions beyond role
    permissions = Column(
        JSONB,
        nullable=True,
        comment="Optional: Additional permissions beyond standard role (JSONB)"
    )

    # Invitation Message (optional)
    message = Column(
        Text,
        nullable=True,
        comment="Optional personalized message from inviter"
    )

    # Relationships - Inviter
    invited_by_admin_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Admin who sent the invitation"
    )

    # Timestamps
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        comment="When invitation was created"
    )

    expires_at = Column(
        DateTime(timezone=True),
        nullable=False,
        comment="When invitation expires"
    )

    accepted_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="When invitation was accepted"
    )

    # Relationships - Accepter
    accepted_by_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="User who accepted the invitation"
    )

    # Declined tracking
    declined_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="When invitation was declined (if declined)"
    )

    declined_reason = Column(
        Text,
        nullable=True,
        comment="Reason for declining (optional)"
    )

    # Revoked tracking
    revoked_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="When invitation was revoked"
    )

    revoked_by_admin_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Admin who revoked the invitation"
    )

    revoked_reason = Column(
        Text,
        nullable=True,
        comment="Reason for revoking (optional)"
    )

    # Constraints
    __table_args__ = (
        Index(
            'uq_admin_invitation_email_pending',
            'email',
            unique=True,
            postgresql_where=text("status = 'pending'")
        ),
        {
            'comment': 'Platform admin invitations - For inviting platform-level administrators'
        }
    )

    # SQLAlchemy Relationships
    invited_by = relationship(
        "Users",
        foreign_keys=[invited_by_admin_id],
        back_populates="sent_admin_invitations"
    )

    accepted_by = relationship(
        "Users",
        foreign_keys=[accepted_by_user_id],
        back_populates="accepted_admin_invitations"
    )

    revoked_by = relationship(
        "Users",
        foreign_keys=[revoked_by_admin_id],
        back_populates="revoked_admin_invitations"
    )

    # to_dict() inherited from SerializableMixin

    def is_expired(self) -> bool:
        """Check if invitation has expired."""
        return datetime.now(timezone.utc) > self.expires_at

    def is_pending(self) -> bool:
        """Check if invitation is pending."""
        return self.status == "pending" and not self.is_expired()

    def can_be_accepted(self) -> bool:
        """Check if invitation can be accepted."""
        return self.status == "pending" and not self.is_expired()

    def __repr__(self):
        return (
            f"<PlatformAdminInvitation("
            f"id={self.id}, "
            f"email={self.email}, "
            f"admin_role={self.admin_role}, "
            f"status={self.status}, "
            f"created_at={self.created_at}"
            f")>"
        )
