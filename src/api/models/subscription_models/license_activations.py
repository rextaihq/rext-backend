from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from src.api.database.base import Base
from src.api.models.base import SerializableMixin
from src.api.models.mixins import UUIDPrimaryKeyMixin


class LicenseActivation(Base, SerializableMixin, UUIDPrimaryKeyMixin):
    __tablename__ = "license_activations"

    # id provided by mixin
    license_id = Column(
        UUID(as_uuid=True),
        ForeignKey("licenses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    instance_id = Column(
        String(255),
        nullable=False,
        index=True,
        comment="Device ID, domain, or unique instance identifier",
    )

    instance_name = Column(
        String(255), nullable=True, comment="Human-readable name for the instance"
    )

    is_active = Column(Boolean, default=True, nullable=False, index=True)

    activated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.current_timestamp()
    )

    deactivated_at = Column(DateTime(timezone=True), nullable=True)

    last_checked_at = Column(
        DateTime(timezone=True),
        nullable=True,
        comment="Last time this activation was validated/checked",
    )

    activation_metadata = Column(
        JSONB, default=dict, nullable=False, comment="Additional info: IP, user agent, OS, etc."
    )

    # Relationships
    license = relationship("License", back_populates="activations", lazy="joined")

    # Table arguments - composite indexes for query optimization
    __table_args__ = (
        # Composite index for finding activations by license and instance
        Index("idx_license_activations_license_instance", "license_id", "instance_id"),
        # Index for finding active activations
        Index("idx_license_activations_active", "license_id", "is_active"),
    )

    def __repr__(self) -> str:
        return (
            f"<LicenseActivation(id={self.id}, license_id={self.license_id}, "
            f"instance={self.instance_id}, active={self.is_active})>"
        )

    def deactivate(self):
        from datetime import timezone

        self.is_active = False
        self.deactivated_at = datetime.now(timezone.utc)
