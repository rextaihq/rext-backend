"""License model for LemonSqueezy one-time purchases."""
import uuid
import enum
from datetime import datetime, timezone
from sqlalchemy import DateTime
from sqlalchemy import Column, String, Integer, ForeignKey, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from src.api.database.base import Base
from src.api.models.base import SerializableMixin


class LicenseStatus(str, enum.Enum):
    """License status enum."""
    ACTIVE = "active"
    INACTIVE = "inactive"
    EXPIRED = "expired"
    DISABLED = "disabled"


class License(Base, SerializableMixin):
    """License model for one-time purchase products."""
    __tablename__ = "licenses"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=True, nullable=False)

    # User association (nullable - user might not have account yet)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)

    # License details
    license_key = Column(String(255), nullable=False, unique=True, index=True)
    lemonsqueezy_license_id = Column(String(255), nullable=False, unique=True, index=True)
    lemonsqueezy_order_id = Column(String(255), nullable=False)
    lemonsqueezy_product_id = Column(String(255), nullable=False)
    product_name = Column(String(255), nullable=False)

    # Status and activation (create_type=False prevents SQLAlchemy from auto-creating the enum)
    # values_callable ensures SQLAlchemy uses the .value (lowercase) not .name (uppercase)
    status = Column(SQLEnum(LicenseStatus, name='licensestatus', create_type=False, values_callable=lambda x: [e.value for e in x]), default=LicenseStatus.INACTIVE, nullable=False, index=True)
    activation_email = Column(String(255), nullable=False, index=True)
    activation_limit = Column(Integer, nullable=True)  # Null = unlimited activations
    activation_count = Column(Integer, default=0, nullable=False)

    # Timestamps
    activated_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)  # Null = lifetime license
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    # License metadata for extensibility (using license_metadata to avoid reserved word)
    license_metadata = Column(JSONB, default=dict, nullable=False)

    # Relationships
    user = relationship("Users", back_populates="licenses")
    activations = relationship("LicenseActivation", back_populates="license", cascade="all, delete-orphan", passive_deletes=True)

    def __repr__(self):
        return f"<License(id={self.id}, key={self.license_key[:12]}..., status={self.status.value})>"

    def to_dict(self, **kwargs):
        """Custom serialization handling enum values."""
        data = super().to_dict(exclude=['lemonsqueezy_license_id', 'lemonsqueezy_order_id'], **kwargs)
        # Handle enum serialization
        if isinstance(self.status, LicenseStatus):
            data['status'] = self.status.value
        return data

    @property
    def is_valid(self) -> bool:
        """Check if license is currently valid."""
        if self.status != LicenseStatus.ACTIVE:
            return False
        if self.expires_at and self.expires_at < datetime.now(timezone.utc):
            return False
        if self.activation_limit and self.activation_count >= self.activation_limit:
            return False
        return True

    @property
    def is_expired(self) -> bool:
        """Check if license has expired."""
        if self.expires_at and self.expires_at < datetime.now(timezone.utc):
            return True
        return False

    @property
    def can_activate(self) -> bool:
        """Check if license can be activated (within activation limit)."""
        if self.activation_limit is None:
            return True
        return self.activation_count < self.activation_limit
