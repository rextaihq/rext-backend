"""
Discount Usage model for tracking discount code usage.

This model records when users apply discount codes during checkout,
enabling analytics and fraud prevention.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import String, Numeric, TIMESTAMP, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from src.api.database.base import Base
from src.api.models.base import SerializableMixin


class DiscountUsage(Base, SerializableMixin):
    """
    Track discount code usage for analytics and fraud prevention.

    Each record represents one instance of a user applying a discount code.
    This data is typically created by webhook handlers when an order is processed.
    """

    __tablename__ = "discount_usage"

    # Primary key
    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid()
    )

    # Foreign keys
    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    subscription_id: Mapped[Optional[UUID]] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("user_subscriptions.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )

    # Discount information
    discount_code: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True
    )

    discount_amount: Mapped[Optional[float]] = mapped_column(
        Numeric(10, 2),
        nullable=True,
        comment="Amount saved (in currency or percentage)"
    )

    discount_amount_type: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
        comment="Type: 'percent' or 'fixed'"
    )

    # LemonSqueezy references
    order_id: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="LemonSqueezy order ID"
    )

    lemonsqueezy_discount_id: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        comment="LemonSqueezy discount ID"
    )

    # Metadata
    applied_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.current_timestamp(),
        index=True
    )

    usage_metadata: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True,
        comment="Additional discount information from LemonSqueezy"
    )

    # Relationships
    user: Mapped["Users"] = relationship(
        "Users",
        back_populates="discount_usages",
        lazy="joined"
    )

    subscription: Mapped[Optional["UserSubscription"]] = relationship(
        "UserSubscription",
        back_populates="discount_usages",
        lazy="select"
    )

    def __repr__(self) -> str:
        return (
            f"<DiscountUsage(id={self.id}, user_id={self.user_id}, "
            f"code={self.discount_code}, amount={self.discount_amount})>"
        )

    def to_dict(self) -> dict:
        """Convert model to dictionary."""
        return {
            "id": str(self.id),
            "user_id": str(self.user_id),
            "subscription_id": str(self.subscription_id) if self.subscription_id else None,
            "discount_code": self.discount_code,
            "discount_amount": float(self.discount_amount) if self.discount_amount else None,
            "discount_amount_type": self.discount_amount_type,
            "order_id": self.order_id,
            "lemonsqueezy_discount_id": self.lemonsqueezy_discount_id,
            "applied_at": self.applied_at.isoformat() if self.applied_at else None,
            "metadata": self.usage_metadata
        }
