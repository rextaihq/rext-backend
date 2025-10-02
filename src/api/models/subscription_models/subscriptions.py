"""User subscription model."""
import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, TIMESTAMP, ForeignKey, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
import enum
from src.api.database.database import Base


class SubscriptionStatus(str, enum.Enum):
    """Subscription status enum."""
    ACTIVE = "active"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    TRIAL = "trial"
    SUSPENDED = "suspended"


class BillingPeriod(str, enum.Enum):
    """Billing period enum."""
    MONTHLY = "monthly"
    YEARLY = "yearly"
    LIFETIME = "lifetime"


class UserSubscription(Base):
    """User subscription model tracking active subscriptions."""
    __tablename__ = "user_subscriptions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=True, nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    plan_id = Column(UUID(as_uuid=True), ForeignKey("subscription_plans.id"), nullable=False)

    # Subscription details
    status = Column(SQLEnum(SubscriptionStatus), default=SubscriptionStatus.ACTIVE, nullable=False)
    billing_period = Column(SQLEnum(BillingPeriod), default=BillingPeriod.MONTHLY, nullable=False)

    # Dates
    start_date = Column(TIMESTAMP, default=datetime.utcnow, nullable=False)
    end_date = Column(TIMESTAMP, nullable=True)  # Null for active subscriptions
    trial_end_date = Column(TIMESTAMP, nullable=True)
    cancelled_at = Column(TIMESTAMP, nullable=True)

    # Payment integration
    stripe_subscription_id = Column(String(255), unique=True)
    stripe_customer_id = Column(String(255))

    # Usage tracking (reset monthly)
    current_api_calls = Column(Integer, default=0)
    usage_reset_date = Column(TIMESTAMP, default=datetime.utcnow)

    # Metadata
    subscription_metadata = Column(JSONB, default=dict)

    created_at = Column(TIMESTAMP, default=datetime.utcnow, nullable=False)
    updated_at = Column(TIMESTAMP, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("Users", backref="subscriptions")
    plan = relationship("SubscriptionPlan", back_populates="subscriptions")

    def to_dict(self):
        """Convert model to dictionary."""
        return {
            "id": str(self.id),
            "user_id": str(self.user_id),
            "plan_id": str(self.plan_id),
            "status": self.status.value,
            "billing_period": self.billing_period.value,
            "start_date": self.start_date.isoformat() if self.start_date else None,
            "end_date": self.end_date.isoformat() if self.end_date else None,
            "trial_end_date": self.trial_end_date.isoformat() if self.trial_end_date else None,
            "cancelled_at": self.cancelled_at.isoformat() if self.cancelled_at else None,
            "current_api_calls": self.current_api_calls,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
