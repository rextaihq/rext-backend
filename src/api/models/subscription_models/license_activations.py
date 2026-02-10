"""
License Activation model for tracking individual device/instance activations.

This model records each activation of a license key to a specific device or instance,
enabling activation limit enforcement and management.
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Column, String, ForeignKey, TIMESTAMP, Boolean, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship, Mapped, mapped_column
from sqlalchemy.sql import func

from src.api.database.base import Base
from src.api.models.base import SerializableMixin


class LicenseActivation(Base, SerializableMixin):
    """
    Track individual license activations to devices/instances.

    Each record represents one activation of a license key to a specific
    device, domain, or instance identifier.
    """

    __tablename__ = "license_activations"

    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        unique=True,
        nullable=False
    )

    # Foreign keys
    license_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("licenses.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Activation details
    instance_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
        comment="Device ID, domain, or unique instance identifier"
    )

    instance_name: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="Human-readable name for the instance"
    )

    # Status
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        index=True
    )

    # Timestamps
    activated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.current_timestamp()
    )

    deactivated_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True
    )

    last_checked_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
        comment="Last time this activation was validated/checked"
    )

    # Metadata
    activation_metadata: Mapped[dict] = mapped_column(
        JSONB,
        default=dict,
        nullable=False,
        comment="Additional info: IP, user agent, OS, etc."
    )

    # Relationships
    license: Mapped["License"] = relationship(
        "License",
        back_populates="activations",
        lazy="joined"
    )

    # Table arguments - composite indexes for query optimization
    __table_args__ = (
        # Composite index for finding activations by license and instance
        Index('idx_license_activations_license_instance', 'license_id', 'instance_id'),
        # Index for finding active activations
        Index('idx_license_activations_active', 'license_id', 'is_active'),
    )

    def __repr__(self) -> str:
        return (
            f"<LicenseActivation(id={self.id}, license_id={self.license_id}, "
            f"instance={self.instance_id}, active={self.is_active})>"
        )

    def to_dict(self, **kwargs):
        """Custom serialization."""
        data = super().to_dict(**kwargs)
        # Convert UUIDs to strings
        if 'id' in data and isinstance(data['id'], uuid.UUID):
            data['id'] = str(data['id'])
        if 'license_id' in data and isinstance(data['license_id'], uuid.UUID):
            data['license_id'] = str(data['license_id'])
        return data

    def deactivate(self):
        """Mark this activation as inactive."""
        self.is_active = False
        self.deactivated_at = datetime.utcnow()
