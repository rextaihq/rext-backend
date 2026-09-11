"""Order model — the local record of every LemonSqueezy purchase.

LemonSqueezy owns the money; this table owns what that money means to us. It is
written from webhooks so the billing UI, refunds and entitlement checks never
have to call the LemonSqueezy API on the request path.

It also makes an order id *resolvable*: before this table existed the only way
to map a LemonSqueezy order back to a user was `licenses` (LTDs only) or
`user_subscriptions.lemonsqueezy_order_id` (populated inconsistently), so any
other order id could not be refunded.
"""

import uuid
from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
)
from sqlalchemy import (
    Enum as SQLEnum,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import relationship

from src.api.database.base import Base
from src.api.models.base import SerializableMixin


class OrderStatus(str, Enum):
    """Order status, mirroring LemonSqueezy's order statuses."""

    PENDING = "pending"
    PAID = "paid"
    FAILED = "failed"
    REFUNDED = "refunded"
    PARTIAL_REFUND = "partial_refund"


class Order(Base, SerializableMixin):
    """A single purchase recorded from LemonSqueezy.

    Covers both one-time purchases and each recurring subscription charge, so
    billing history is one query against one table.
    """

    __tablename__ = "orders"

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

    # Null for one-time purchases; set for orders raised by a subscription.
    subscription_id = Column(
        PGUUID(as_uuid=True),
        ForeignKey("user_subscriptions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # ==============================
    # LEMONSQUEEZY IDS
    # ==============================
    # Unique so webhook retries upsert rather than duplicate.
    lemonsqueezy_order_id = Column(String(255), nullable=False, unique=True, index=True)
    lemonsqueezy_customer_id = Column(String(255), nullable=True, index=True)
    lemonsqueezy_subscription_id = Column(String(255), nullable=True, index=True)
    lemonsqueezy_product_id = Column(String(255), nullable=True)
    lemonsqueezy_variant_id = Column(String(255), nullable=True, index=True)

    # ==============================
    # ORDER DETAILS
    # ==============================
    product_name = Column(String(255), nullable=True)

    # Amounts are in cents, matching both LemonSqueezy and the refunds table.
    total = Column(Integer, nullable=False, default=0)
    subtotal = Column(Integer, nullable=True)
    tax = Column(Integer, nullable=True)
    currency = Column(String(3), nullable=False, default="USD")

    status = Column(
        SQLEnum(
            OrderStatus,
            name="orderstatus",
            create_constraint=True,
            values_callable=lambda obj: [e.value for e in obj],
        ),
        nullable=False,
        default=OrderStatus.PENDING,
        index=True,
    )

    # LemonSqueezy-hosted receipt. We never generate the financial document.
    receipt_url = Column(String(1024), nullable=True)

    # ==============================
    # TIMESTAMPS
    # ==============================
    refunded_at = Column(DateTime(timezone=True), nullable=True)
    ordered_at = Column(DateTime(timezone=True), nullable=True, index=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
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
    user = relationship("Users", back_populates="orders")
    subscription = relationship("UserSubscription", back_populates="orders")

    def __repr__(self) -> str:
        return (
            f"<Order(id={self.id}, "
            f"lemonsqueezy_order_id={self.lemonsqueezy_order_id}, "
            f"total={self.total}, "
            f"status={self.status})>"
        )
