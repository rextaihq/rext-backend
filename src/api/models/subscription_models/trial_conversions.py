"""Trial conversion tracking model."""
from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import Column, String, Integer, ForeignKey, DateTime, Numeric
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship

from src.api.database.base import Base
from src.api.models.base import SerializableMixin
from src.api.models.mixins import UUIDPrimaryKeyMixin, TimestampMixin


class TrialConversion(Base, SerializableMixin, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "trial_conversions"

    # id, created_at provided by mixins
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    subscription_id = Column(
        UUID(as_uuid=True),
        ForeignKey("user_subscriptions.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    trial_started_at = Column(
        DateTime(timezone=True),
        nullable=False,
        comment="When the trial started"
    )

    trial_ended_at = Column(
        DateTime(timezone=True),
        nullable=False,
        comment="When the trial ended"
    )

    converted_at = Column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False,
        index=True,
        comment="When trial converted to paid"
    )

    trial_duration_days = Column(
        Integer,
        nullable=False,
        comment="Total trial duration in days"
    )

    conversion_plan_id = Column(
        UUID(as_uuid=True),
        ForeignKey("subscription_plans.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Plan user converted to"
    )

    conversion_billing_period = Column(
        String(20),
        nullable=False,
        comment="Monthly or yearly"
    )

    conversion_amount = Column(
        Numeric(10, 2),
        nullable=True,
        comment="First payment amount"
    )

    conversion_metadata = Column(
        JSONB,
        default=dict,
        nullable=False,
        comment="Additional conversion data (discount code, source, etc.)"
    )

    # created_at provided by TimestampMixin

    # SAME relationships – NOT changed
    user = relationship("Users", backref="trial_conversions")
    subscription = relationship("UserSubscription", backref="trial_conversions")
    plan = relationship("SubscriptionPlan", backref="trial_conversions")

    def __repr__(self):
        return f"<TrialConversion(id={self.id}, user_id={self.user_id}, converted_at={self.converted_at})>"

    @property
    def conversion_rate_days(self) -> int:
        if self.converted_at and self.trial_started_at:
            return (self.converted_at - self.trial_started_at).days
        return 0
