"""
Discount Usage model for tracking discount code usage.

This model records when users apply discount codes during checkout,
enabling analytics and fraud prevention.
"""

from sqlalchemy import Column, String, Numeric, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from src.api.database.base import Base
from src.api.models.base import SerializableMixin
from src.api.models.mixins import UUIDPrimaryKeyMixin


class DiscountUsage(Base, SerializableMixin, UUIDPrimaryKeyMixin):
    __tablename__ = "discount_usage"

    # id provided by mixin (uses uuid4 default instead of server_default)

    user_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    subscription_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("user_subscriptions.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )

    discount_code = Column(
        String(100),
        nullable=False,
        index=True
    )

    discount_amount = Column(
        Numeric(10, 2),
        nullable=True,
        comment="Amount saved (in currency or percentage)"
    )

    discount_amount_type = Column(
        String(20),
        nullable=True,
        comment="Type: 'percent' or 'fixed'"
    )

    order_id = Column(
        String(255),
        nullable=True,
        comment="LemonSqueezy order ID"
    )

    lemonsqueezy_discount_id = Column(
        String(255),
        nullable=True,
        comment="LemonSqueezy discount ID"
    )

    applied_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
        index=True
    )

    usage_metadata = Column(
        JSONB,
        nullable=True,
        comment="Additional discount information from LemonSqueezy"
    )

    # SAME relationships
    user = relationship("Users", back_populates="discount_usages", lazy="joined")
    subscription = relationship("UserSubscription", back_populates="discount_usages", lazy="select")

    def to_dict(self, **kwargs):
        """Convert model to dictionary, renaming metadata for API compatibility."""
        data = super().to_dict(**kwargs)
        if 'usage_metadata' in data:
            data['metadata'] = data.pop('usage_metadata')
        return data


