"""Account-creation IP allowlist model.

Stores the public IPs / CIDR ranges that are allowed to bypass the per-device
cap on creating multiple non-paid accounts (see
``check_device_account_limit`` in ``src/api/routes/users/auth.py``).

Unlike ``TRUSTED_PROXY_IPS`` this list is managed at runtime by platform admins
through the admin API rather than via environment variables.
"""

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID as PostgresUUID

from src.api.database.base import Base
from src.api.models.base import SerializableMixin


class AccountCreationIpAllowlist(Base, SerializableMixin):
    """A single approved IP address or CIDR range for multiple-account creation."""

    __tablename__ = "account_creation_ip_allowlist"

    id = Column(PostgresUUID(as_uuid=True), primary_key=True, default=uuid4)

    # A single IPv4/IPv6 address ("203.0.113.10") or a CIDR network
    # ("203.0.113.0/24", "2001:db8::/32"). Stored normalized (see
    # AccountCreationAllowlistService._normalize). The unique constraint also
    # serves as the lookup index.
    ip_address = Column(String(64), nullable=False, unique=True)

    # Optional human-readable note, e.g. "London office egress" / "CI runners".
    label = Column(String(255), nullable=True)

    # Soft on/off switch so an admin can disable an entry without losing the
    # record of who added it and why. Only active entries bypass the cap.
    is_active = Column(Boolean, nullable=False, default=True, index=True)

    created_by = Column(
        PostgresUUID(as_uuid=True),
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
        nullable=False,
    )
