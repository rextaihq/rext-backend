"""
Credit grants: credits given on top of a subscription's monthly credits.

A grant has its own amount, what is left of it, what was forfeited (a refund
takes an unspent bonus back) and an expiry; spent = amount - remaining -
forfeited. It is spent before the monthly credits, soonest expiry first, and an
expired grant is simply no longer counted. Today every grant is a promotion's bonus and points
at it; one grant per subscription and promotion, so a webhook delivered twice
grants once.
"""

import uuid

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from src.api.database.base import Base
from src.api.models.base import SerializableMixin


class CreditGrant(Base, SerializableMixin):
    __tablename__ = "credit_grants"
    __table_args__ = (
        UniqueConstraint(
            "subscription_id", "promotion_id", name="uq_credit_grants_subscription_promotion"
        ),
        CheckConstraint(
            "remaining >= 0 AND forfeited >= 0 AND remaining + forfeited <= amount",
            name="ck_credit_grants_remaining",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, nullable=False)
    subscription_id = Column(
        UUID(as_uuid=True),
        ForeignKey("user_subscriptions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    promotion_id = Column(
        UUID(as_uuid=True),
        ForeignKey("promotions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    # The Lemon Squeezy order whose payment earned the grant: a refund of that
    # order forfeits it, and a grant is never made for a refunded order.
    lemonsqueezy_order_id = Column(String(255), nullable=True, index=True)
    amount = Column(Integer, nullable=False)
    remaining = Column(Integer, nullable=False)
    forfeited = Column(Integer, nullable=False, server_default="0")
    # NULL never expires.
    expires_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    subscription = relationship("UserSubscription")
    promotion = relationship("Promotion", lazy="selectin")
