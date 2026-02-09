"""User subscription model."""
import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, Boolean, DateTime, ForeignKey, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
import enum
from src.api.database.base import Base
from src.api.models.base import SerializableMixin


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

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=True, nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    plan_id = Column(UUID(as_uuid=True), ForeignKey("subscription_plans.id"), nullable=False)

    # Subscription details
    status = Column(SQLEnum(SubscriptionStatus), default=SubscriptionStatus.ACTIVE, nullable=False)
    billing_period = Column(SQLEnum(BillingPeriod), default=BillingPeriod.MONTHLY, nullable=False)

    # Dates
    start_date = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    end_date = Column(DateTime(timezone=True), nullable=True)  # Null for active subscriptions
    trial_end_date = Column(DateTime(timezone=True), nullable=True)
    cancelled_at = Column(DateTime(timezone=True), nullable=True)

    # Payment Provider Integration (provider-agnostic)
    provider_subscription_id = Column(String(255), unique=True)
    provider_customer_id = Column(String(255))

    # LemonSqueezy Integration Fields
    lemonsqueezy_subscription_id = Column(String(255), nullable=True, unique=True, index=True)  # LemonSqueezy subscription ID
    lemonsqueezy_customer_id = Column(String(255), nullable=True, index=True)  # LemonSqueezy customer ID
    lemonsqueezy_order_id = Column(String(255), nullable=True)  # LemonSqueezy order ID
    lemonsqueezy_product_id = Column(String(255), nullable=True)  # LemonSqueezy product ID
    lemonsqueezy_variant_id = Column(String(255), nullable=True)  # LemonSqueezy variant ID
    renews_at = Column(DateTime(timezone=True), nullable=True, index=True)  # Next renewal date
    ends_at = Column(DateTime(timezone=True), nullable=True)  # Subscription end date
    cancel_at_period_end = Column(Boolean, default=False, nullable=False)  # Cancel at period end flag

    # Payment failure & dunning management
    grace_period_end = Column(DateTime(timezone=True), nullable=True, index=True)  # When to suspend after payment failure
    payment_failed_at = Column(DateTime(timezone=True), nullable=True)  # When payment first failed

    # Usage tracking (reset monthly)
    current_api_calls = Column(Integer, default=0)
    usage_reset_date = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # Metadata
    subscription_metadata = Column(JSONB, default=dict)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    user = relationship("Users", backref="subscriptions")
    plan = relationship("SubscriptionPlan", back_populates="subscriptions")
    discount_usages = relationship("DiscountUsage", back_populates="subscription", cascade="all, delete-orphan")
    refunds = relationship("Refund", back_populates="subscription")

    def to_dict(self, **kwargs):
        """Custom serialization handling enum values"""
        data = super().to_dict(exclude=['provider_subscription_id', 'provider_customer_id', 'subscription_metadata'], **kwargs)
        # Handle enum serialization
        if isinstance(self.status, SubscriptionStatus):
            data['status'] = self.status.value
        if isinstance(self.billing_period, BillingPeriod):
            data['billing_period'] = self.billing_period.value
        return data
