"""User subscription model."""

import enum
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, and_, not_, or_
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from src.api.database.base import Base
from src.api.models.base import SerializableMixin
from src.api.models.subscription_models.plans import SubscriptionPlan


class SubscriptionStatus(str, enum.Enum):
    """Subscription status enum.

    For a Lemon Squeezy subscription the status is Lemon Squeezy's own
    (`lemonsqueezy_status()` maps it), and it decides access: see
    `subscription_grants_access`.
    """

    ACTIVE = "active"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    TRIAL = "trial"
    # Written by the old 7-day payment grace; no longer set (rows were moved to PAST_DUE).
    SUSPENDED = "suspended"
    PAST_DUE = "past_due"  # A renewal failed and Lemon Squeezy is retrying it; access stays
    UNPAID = "unpaid"  # Lemon Squeezy's retries ran out; no access until the card is updated
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
    # Lemon Squeezy's `updated_at` for the state stored here, so a webhook carrying
    # an older state than the row's can be told apart and ignored.
    provider_updated_at = Column(DateTime(timezone=True), nullable=True)

    # Payment failure & dunning management
    grace_period_end = Column(
        DateTime(timezone=True), nullable=True, index=True
    )  # Set by the old 7-day payment grace; no longer written
    payment_failed_at = Column(DateTime(timezone=True), nullable=True)  # When payment first failed

    # Usage tracking (reset monthly)
    current_api_calls = Column(Integer, default=0)
    usage_reset_date = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Credit tracking (new credit-based billing)
    current_credits = Column(Integer, default=0, server_default="0", nullable=False)
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
    orders = relationship("Order", back_populates="subscription")
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


# Lemon Squeezy's subscription statuses (docs.lemonsqueezy.com, the subscription
# object) and the status each is stored as.
_LEMONSQUEEZY_STATUSES = {
    "on_trial": SubscriptionStatus.TRIAL,
    "active": SubscriptionStatus.ACTIVE,
    "paused": SubscriptionStatus.PAUSED,
    "past_due": SubscriptionStatus.PAST_DUE,
    "unpaid": SubscriptionStatus.UNPAID,
    "cancelled": SubscriptionStatus.CANCELLED,
    "expired": SubscriptionStatus.EXPIRED,
}


def lemonsqueezy_status(status: Optional[str]) -> SubscriptionStatus:
    """The stored status for a Lemon Squeezy status string (ACTIVE when unknown)."""
    return _LEMONSQUEEZY_STATUSES.get((status or "").lower(), SubscriptionStatus.ACTIVE)


# The statuses that keep the plan: paid, on trial, or with a failed renewal that
# Lemon Squeezy is still retrying (its dunning, about two weeks). UNPAID and EXPIRED
# lose it; CANCELLED keeps it until end_date (below).
ACCESS_STATUSES = (
    SubscriptionStatus.ACTIVE,
    SubscriptionStatus.TRIAL,
    SubscriptionStatus.PAST_DUE,
)

# A renewal failed and has not been paid since: still retried (PAST_DUE), given up
# on (UNPAID), or left by the old grace period (SUSPENDED). The fix is a new card,
# not another subscription, and the month's credits wait for the payment.
FAILED_PAYMENT_STATUSES = (
    SubscriptionStatus.PAST_DUE,
    SubscriptionStatus.UNPAID,
    SubscriptionStatus.SUSPENDED,
)


def subscription_grants_access(now: Optional[datetime] = None):
    """
    SQLAlchemy filter: the subscription still grants plan access/credits.

    True for a subscription in ACCESS_STATUSES, and ALSO true for a
    subscription the user has already cancelled but whose paid-through
    `end_date` hasn't passed yet - cancelling flips `status` to CANCELLED
    immediately (so the UI/re-cancel checks reflect it right away), but the
    user keeps their plan's credits and limits until `end_date`.

    A trial grants access until its own end date. An unpaid trial (no Lemon
    Squeezy subscription) whose `trial_end_date` has passed grants nothing, even
    before the daily expiry job sets it EXPIRED, so it can't spend its credits for
    up to a day after it ended (F16a, rext-control #480). A paid plan's trial days
    at Lemon Squeezy are left to Lemon Squeezy, which converts or ends them.

    A known duplicate never grants anything: one settled here (`duplicate_of`), or
    found and left to a person (`duplicate_found_of`). The customer's kept
    subscription gives the plan, and a refunded duplicate's paid-through end
    must not give it back (duplicate_subscriptions.py).
    """
    now = now or datetime.now(timezone.utc)
    trial_ended = and_(
        UserSubscription.status == SubscriptionStatus.TRIAL,
        UserSubscription.trial_end_date.isnot(None),
        UserSubscription.trial_end_date <= now,
        UserSubscription.lemonsqueezy_subscription_id.is_(None),
    )
    return and_(
        or_(
            and_(UserSubscription.status.in_(ACCESS_STATUSES), not_(trial_ended)),
            and_(
                UserSubscription.status == SubscriptionStatus.CANCELLED,
                UserSubscription.end_date.isnot(None),
                UserSubscription.end_date > now,
            ),
        ),
        not_a_known_duplicate(),
    )


def not_a_known_duplicate():
    """SQLAlchemy filter: the row isn't a duplicate settled here or left to a person."""
    return or_(
        UserSubscription.subscription_metadata.is_(None),
        ~or_(
            UserSubscription.subscription_metadata.has_key("duplicate_of"),
            UserSubscription.subscription_metadata.has_key("duplicate_found_of"),
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
