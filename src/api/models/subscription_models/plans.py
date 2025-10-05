"""Subscription plan model."""
import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, Numeric, Boolean, Text, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from src.api.database.database import Base


class SubscriptionPlan(Base):
    """Subscription plan model defining available tiers."""
    __tablename__ = "subscription_plans"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=True, nullable=False)
    name = Column(String(100), unique=True, nullable=False)  # e.g., "free", "pro", "enterprise"
    display_name = Column(String(150), nullable=False)  # e.g., "Free Tier", "Pro Plan"
    description = Column(Text)

    # Pricing
    price_monthly = Column(Numeric(10, 2), default=0.00)  # Monthly price in USD
    price_yearly = Column(Numeric(10, 2), default=0.00)  # Yearly price in USD

    # Feature limits
    features = Column(JSONB, default=dict)  # Flexible JSON for features
    max_workspaces = Column(Integer, default=1)
    max_members_per_workspace = Column(Integer, default=5)
    max_topics = Column(Integer, default=100)
    max_knowledge_items = Column(Integer, default=1000)
    max_api_calls_per_month = Column(Integer, default=10000)

    # Status
    is_active = Column(Boolean, default=True)
    is_public = Column(Boolean, default=True)  # Public plans shown on pricing page

    # Metadata
    stripe_price_id_monthly = Column(String(255))  # Stripe integration
    stripe_price_id_yearly = Column(String(255))

    created_at = Column(TIMESTAMP, default=datetime.utcnow, nullable=False)
    updated_at = Column(TIMESTAMP, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    subscriptions = relationship("UserSubscription", back_populates="plan")

    def to_dict(self):
        """Convert model to dictionary."""
        return {
            "id": str(self.id),
            "name": self.name,
            "display_name": self.display_name,
            "description": self.description,
            "price_monthly": float(self.price_monthly) if self.price_monthly else 0.0,
            "price_yearly": float(self.price_yearly) if self.price_yearly else 0.0,
            "features": self.features,
            "max_workspaces": self.max_workspaces,
            "max_members_per_workspace": self.max_members_per_workspace,
            "max_topics": self.max_topics,
            "max_knowledge_items": self.max_knowledge_items,
            "max_api_calls_per_month": self.max_api_calls_per_month,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
