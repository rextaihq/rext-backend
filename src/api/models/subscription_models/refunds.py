"""Refund model for tracking refund operations."""

import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import (
    Boolean,
    Column,
    ForeignKey,
    Integer,
    String,
    Text,
    TIMESTAMP,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import relationship

from src.api.database.base import Base
from src.api.models.base import SerializableMixin


class RefundStatus(str, Enum):
    """Refund status enumeration."""

    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"


class Refund(Base, SerializableMixin):
    """
    Refund model for tracking refund operations.
    """

    __tablename__ = "refunds"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # ==============================
    # FOREIGN KEYS
    # ==============================
    user_id = Column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    subscription_id = Column(
        PGUUID(as_uuid=True),
        ForeignKey("user_subscriptions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # ==============================
    # LEMONSQUEEZY IDS
    # ==============================
    lemonsqueezy_order_id = Column(String, nullable=False, index=True)
    lemonsqueezy_refund_id = Column(String, nullable=True, index=True)

    # ==============================
    # REFUND DETAILS
    # ==============================
    refund_amount = Column(Integer, nullable=False)
    original_amount = Column(Integer, nullable=False)
    currency = Column(String(3), nullable=False, default="USD")
    reason = Column(Text, nullable=True)

    # ==============================
    # STATUS
    # ==============================
    status = Column(
        String(20),
        nullable=False,
        default=RefundStatus.PENDING,
        index=True,
    )
    is_partial = Column(Boolean, nullable=False, default=False)

    # ==============================
    # TIMESTAMPS
    # ==============================
    processed_at = Column(TIMESTAMP, nullable=True)
    created_at = Column(TIMESTAMP, nullable=False, default=datetime.utcnow)
    updated_at = Column(
        TIMESTAMP,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )

    # ==============================
    # RELATIONSHIPS
    # ==============================
    user = relationship("Users", back_populates="refunds")
    subscription = relationship("UserSubscription", back_populates="refunds")

    def __repr__(self) -> str:
        return (
            f"<Refund(id={self.id}, "
            f"user_id={self.user_id}, "
            f"amount={self.refund_amount}, "
            f"status={self.status})>"
        )
