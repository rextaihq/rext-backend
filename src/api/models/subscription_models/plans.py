"""Subscription plan model."""
import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, Numeric, Boolean, Text, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from src.api.database.base import Base
from src.api.models.base import SerializableMixin


class SubscriptionPlan(Base, SerializableMixin):
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

    # Payment Provider Integration (provider-agnostic)
    provider_price_id_monthly = Column(String(255))  # Payment provider price ID (monthly)
    provider_price_id_yearly = Column(String(255))  # Payment provider price ID (yearly)

    # LemonSqueezy Integration Fields
    lemonsqueezy_product_id = Column(String(255), nullable=True, index=True)  # LemonSqueezy product ID
    lemonsqueezy_variant_id_monthly = Column(String(255), nullable=True, index=True)  # LemonSqueezy variant ID (monthly)
    lemonsqueezy_variant_id_yearly = Column(String(255), nullable=True, index=True)  # LemonSqueezy variant ID (yearly)
    lemonsqueezy_store_id = Column(String(255), nullable=True)  # LemonSqueezy store ID

    created_at = Column(TIMESTAMP, default=datetime.utcnow, nullable=False)
    updated_at = Column(TIMESTAMP, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    subscriptions = relationship("UserSubscription", back_populates="plan")

    # to_dict() inherited from SerializableMixin
