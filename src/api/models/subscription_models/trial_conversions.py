"""Trial conversion tracking model."""
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional
from sqlalchemy import Column, String, Integer, ForeignKey, TIMESTAMP, Numeric
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship, Mapped, mapped_column
from src.api.database.base import Base
from src.api.models.base import SerializableMixin


class TrialConversion(Base, SerializableMixin):
    """
    Track when trials convert to paid subscriptions.

    This table provides analytics on trial conversion rates,
    conversion timing, and revenue impact.
    """
    __tablename__ = "trial_conversions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        unique=True,
        nullable=False
    )

    # User and subscription references
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    subscription_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("user_subscriptions.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Trial timeline
    trial_started_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        comment="When the trial started"
    )
    trial_ended_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        comment="When the trial ended"
    )
    converted_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        default=datetime.utcnow,
        nullable=False,
        index=True,
        comment="When trial converted to paid"
    )
    trial_duration_days: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Total trial duration in days"
    )

    # Conversion details
    conversion_plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("subscription_plans.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Plan user converted to"
    )
    conversion_billing_period: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Monthly or yearly"
    )
    conversion_amount: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(10, 2),
        nullable=True,
        comment="First payment amount"
    )

    # Metadata for extensibility
    conversion_metadata: Mapped[dict] = mapped_column(
        JSONB,
        default=dict,
        nullable=False,
        comment="Additional conversion data (discount code, source, etc.)"
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        default=datetime.utcnow,
        nullable=False
    )

    # Relationships
    user = relationship("Users", back_populates="trial_conversions")
    subscription = relationship("UserSubscription", back_populates="trial_conversions")
    plan = relationship("SubscriptionPlan", back_populates="trial_conversions")

    def __repr__(self):
        return f"<TrialConversion(id={self.id}, user_id={self.user_id}, converted_at={self.converted_at})>"

    @property
    def conversion_rate_days(self) -> int:
        """Calculate how many days into trial the conversion happened."""
        if self.converted_at and self.trial_started_at:
            delta = self.converted_at - self.trial_started_at
            return delta.days
        return 0
