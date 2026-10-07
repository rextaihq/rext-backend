"""
Credit grants: credits given on top of a subscription's monthly credits.

A grant has its own amount, what is left of it, what was forfeited (a refund
takes an unspent bonus back, an admin's deduction takes added credits back) and
an expiry; spent = amount - remaining - forfeited. A grant with an expiry is
spent before the monthly credits, soonest expiry first; one without is spent
after them, oldest first; an expired grant is simply no longer counted.

A grant comes from one of two sources. A promotion's bonus (``source =
'promotion'``) points at its promotion; one grant per subscription and
promotion, so a webhook delivered twice grants once. Credits a super admin adds
(``source = 'admin'``, src/services/admin_credits.py) point at no promotion and
carry the admin's reason and who added them.
"""

import uuid

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
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
        # PostgreSQL treats NULLs as distinct here, so a subscription can hold any
        # number of admin grants (promotion_id NULL) and still one per promotion.
        UniqueConstraint(
            "subscription_id", "promotion_id", name="uq_credit_grants_subscription_promotion"
        ),
        CheckConstraint(
            "remaining >= 0 AND forfeited >= 0 AND remaining + forfeited <= amount",
            name="ck_credit_grants_remaining",
        ),
        CheckConstraint(
            "(source = 'promotion' AND promotion_id IS NOT NULL)"
            " OR (source = 'admin' AND reason IS NOT NULL)",
            name="ck_credit_grants_source",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, nullable=False)
    subscription_id = Column(
        UUID(as_uuid=True),
        ForeignKey("user_subscriptions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # "promotion" (a promotion's bonus) or "admin" (added by a super admin).
    source = Column(String(20), nullable=False, server_default="promotion")
    # NULL for an admin grant.
    promotion_id = Column(
        UUID(as_uuid=True),
        ForeignKey("promotions.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    # An admin grant's reason, shown to the customer, and the admin who added it.
    reason = Column(Text, nullable=True)
    granted_by = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
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
