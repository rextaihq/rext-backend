"""Customer-initiated refund requests.

Deliberately separate from `refunds`, which records money actually returned:

- `RefundService.list_refunds` sums `refund_amount` for its reporting summary,
  so requests and rejections living there would count money that was never
  refunded.
- `create_refund` guards on "a refund already exists for this order", which a
  mere request would trip, blocking the admin from doing the real refund.

A rejected request is not a refund. Keeping the two apart keeps both honest.
"""

import uuid
from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import (
    Column,
    DateTime,
    Enum as SQLEnum,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import relationship

from src.api.database.base import Base
from src.api.models.base import SerializableMixin


# How long after purchase a customer may ask for a refund. Requests against
# older orders are refused up front rather than reaching an admin.
REFUND_REQUEST_WINDOW_DAYS = 14


class RefundRequestStatus(str, Enum):
    """Lifecycle of a customer's refund request."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class RefundRequest(Base, SerializableMixin):
    """A customer asking a super admin to refund one of their orders."""

    __tablename__ = "refund_requests"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # ==============================
    # WHO AND WHAT
    # ==============================
    user_id = Column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    order_id = Column(
        PGUUID(as_uuid=True),
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Denormalised so the request survives as an audit record and can be acted
    # on without a join.
    lemonsqueezy_order_id = Column(String(255), nullable=False, index=True)

    # Cents. Full-order refunds only for now, so this mirrors the order total
    # and exists to keep partial requests possible later without a migration.
    requested_amount = Column(Integer, nullable=False)
    currency = Column(String(3), nullable=False, default="USD")

    # The customer's own words. Required — an admin needs a reason to judge.
    reason = Column(Text, nullable=False)

    # ==============================
    # REVIEW
    # ==============================
    status = Column(
        SQLEnum(
            RefundRequestStatus,
            name="refundrequeststatus",
            create_constraint=True,
            values_callable=lambda obj: [e.value for e in obj],
        ),
        nullable=False,
        default=RefundRequestStatus.PENDING,
        index=True,
    )

    reviewed_by_user_id = Column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    admin_note = Column(Text, nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)

    # Set when approval produced an actual refund, linking request to outcome.
    refund_id = Column(
        PGUUID(as_uuid=True),
        ForeignKey("refunds.id", ondelete="SET NULL"),
        nullable=True,
    )

    # ==============================
    # TIMESTAMPS
    # ==============================
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # ==============================
    # RELATIONSHIPS
    # ==============================
    user = relationship(
        "Users", foreign_keys=[user_id], back_populates="refund_requests"
    )
    reviewed_by = relationship("Users", foreign_keys=[reviewed_by_user_id])
    order = relationship("Order")
    refund = relationship("Refund")

    def __repr__(self) -> str:
        return (
            f"<RefundRequest(id={self.id}, "
            f"order={self.lemonsqueezy_order_id}, "
            f"status={self.status})>"
        )
