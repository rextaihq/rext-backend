"""Payment method model."""
import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, Boolean, TIMESTAMP, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from src.api.database.base import Base
from src.api.models.base import SerializableMixin


class PaymentMethod(Base, SerializableMixin):
    """Payment method model for storing user payment methods."""
    __tablename__ = "payment_methods"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=True, nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    # Payment provider integration (provider-agnostic)
    provider_payment_method_id = Column(String(255), unique=True, nullable=False)
    provider_customer_id = Column(String(255), nullable=False)

    # Payment method details
    type = Column(String(50), nullable=False)  # card, bank_account, etc.
    is_default = Column(Boolean, default=False, nullable=False)
    status = Column(String(50), default="active", nullable=False)  # active, expired, failed

    # Card-specific fields (optional)
    card_brand = Column(String(50))  # visa, mastercard, amex, etc.
    card_last4 = Column(String(4))
    card_exp_month = Column(Integer())
    card_exp_year = Column(Integer())

    # Billing details
    billing_email = Column(String(255))

    # Metadata (renamed to avoid SQLAlchemy reserved word)
    payment_metadata = Column(JSONB, default=dict)

    created_at = Column(TIMESTAMP, default=datetime.utcnow, nullable=False)
    updated_at = Column(TIMESTAMP, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("Users", back_populates="payment_methods")

    # to_dict() inherited from SerializableMixin

    def __repr__(self):
        return f"<PaymentMethod {self.type} ending in {self.card_last4}>"
