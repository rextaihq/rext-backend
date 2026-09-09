"""User subscription model."""

import enum
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, and_, or_
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from src.api.database.base import Base
from src.api.models.base import SerializableMixin
from src.api.models.subscription_models.plans import SubscriptionPlan


class SubscriptionStatus(str, enum.Enum):
    """Subscription status enum."""

    ACTIVE = "active"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    TRIAL = "trial"
    SUSPENDED = "suspended"
    PAST_DUE = "past_due"  # Payment failed, retrying
    PAUSED = "paused"  # Subscription temporarily paused


class BillingPeriod(str, enum.Enum):
    """Billing period enum."""

    MONTHLY = "monthly"
    YEARLY = "yearly"
    LIFETIME = "lifetime"


class UserSubscription(Base, SerializableMixin):
    """User subscription model tracking active subscriptions."""

    __tablename__ = "user_subscriptions"

    id = Column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=True, nullable=False
    )
    user_id = Column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    plan_id = Column(
        UUID(as_uuid=True),
        ForeignKey("subscription_plans.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # Subscription details
    status = Column(SQLEnum(SubscriptionStatus), default=SubscriptionStatus.ACTIVE, nullable=False)
    billing_period = Column(SQLEnum(BillingPeriod), default=BillingPeriod.MONTHLY, nullable=False)

    # Dates
    start_date = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    end_date = Column(DateTime(timezone=True), nullable=True)  # Null for active subscriptions
    trial_end_date = Column(DateTime(timezone=True), nullable=True)
    cancelled_at = Column(DateTime(timezone=True), nullable=True)
    cancellation_reason = Column(Text, nullable=True)

    # Payment Provider Integration (provider-agnostic)
    provider_subscription_id = Column(String(255), unique=True)
    provider_customer_id = Column(String(255))

    # LemonSqueezy Integration Fields
    lemonsqueezy_subscription_id = Column(
        String(255), nullable=True, unique=True, index=True
    )  # LemonSqueezy subscription ID
    lemonsqueezy_customer_id = Column(
        String(255), nullable=True, index=True
    )  # LemonSqueezy customer ID
    lemonsqueezy_order_id = Column(String(255), nullable=True)  # LemonSqueezy order ID
    lemonsqueezy_product_id = Column(String(255), nullable=True)  # LemonSqueezy product ID
    lemonsqueezy_variant_id = Column(String(255), nullable=True)  # LemonSqueezy variant ID
    renews_at = Column(DateTime(timezone=True), nullable=True, index=True)  # Next renewal date
    ends_at = Column(DateTime(timezone=True), nullable=True)  # Subscription end date
    cancel_at_period_end = Column(
        Boolean, default=False, nullable=False
    )  # Cancel at period end flag

    # Payment failure & dunning management
    grace_period_end = Column(
        DateTime(timezone=True), nullable=True, index=True
    )  # When to suspend after payment failure
    payment_failed_at = Column(DateTime(timezone=True), nullable=True)  # When payment first failed

    # Usage tracking (reset monthly)
    current_api_calls = Column(Integer, default=0)
    usage_reset_date = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Credit tracking (new credit-based billing)
    current_credits = Column(Integer, default=0)
    credits_reset_date = Column(DateTime(timezone=True), nullable=True)

    # Metadata
    subscription_metadata = Column(JSONB, default=dict)

    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    user = relationship("Users", back_populates="subscriptions")
    plan = relationship("SubscriptionPlan", back_populates="subscriptions")
    discount_usages = relationship(
        "DiscountUsage",
        back_populates="subscription",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    refunds = relationship("Refund", back_populates="subscription")
    trial_conversions = relationship("TrialConversion", back_populates="subscription")

    def to_dict(self, **kwargs):
        """Custom serialization handling enum values"""
        data = super().to_dict(
            exclude=["provider_subscription_id", "provider_customer_id", "subscription_metadata"],
            **kwargs,
        )
        # Handle enum serialization
        if isinstance(self.status, SubscriptionStatus):
            data["status"] = self.status.value
        if isinstance(self.billing_period, BillingPeriod):
            data["billing_period"] = self.billing_period.value
        return data


def subscription_grants_access(now: Optional[datetime] = None):
    """
    SQLAlchemy filter: the subscription still grants plan access/credits.

    True for a genuinely active/trial subscription, and ALSO true for a
    subscription the user has already cancelled but whose paid-through
    `end_date` hasn't passed yet - cancelling flips `status` to CANCELLED
    immediately (so the UI/re-cancel checks reflect it right away), but the
    user keeps their plan's credits and limits until `end_date`.
    """
    now = now or datetime.now(timezone.utc)
    return or_(
        UserSubscription.status.in_([SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL]),
        and_(
            UserSubscription.status == SubscriptionStatus.CANCELLED,
            UserSubscription.end_date.isnot(None),
            UserSubscription.end_date > now,
        ),
    )


def subscription_is_active_paid():
    """
    SQLAlchemy filter: the subscription is a currently active, paid (non-trial) plan.

    Requires joining UserSubscription to SubscriptionPlan on plan_id. Used to
    determine whether an account should count toward the per-device free/trial
    account limit (see SubscriptionService.count_non_paid_accounts_for_device).
    """
    return and_(
        UserSubscription.status == SubscriptionStatus.ACTIVE,
        SubscriptionPlan.is_trial_plan.is_(False),
    )
