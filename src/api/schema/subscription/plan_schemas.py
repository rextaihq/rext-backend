"""
Subscription plan schemas for admin management.

This module defines Pydantic models for subscription plan operations.
"""

from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, Dict, Any
from decimal import Decimal


class SubscriptionPlanCreate(BaseModel):
    """Schema for creating a new subscription plan (admin only)."""
    name: str = Field(
        ...,
        min_length=2,
        max_length=100,
        description="Unique plan identifier (lowercase, no spaces)",
        pattern="^[a-z0-9_]+$"
    )
    display_name: str = Field(
        ...,
        min_length=2,
        max_length=150,
        description="Human-readable plan name"
    )
    description: Optional[str] = Field(
        None,
        description="Plan description"
    )
    price_monthly: Decimal = Field(
        default=Decimal("0.00"),
        ge=Decimal("0.00"),
        le=Decimal("99999.99"),
        description="Monthly price in USD"
    )
    price_yearly: Decimal = Field(
        default=Decimal("0.00"),
        ge=Decimal("0.00"),
        le=Decimal("99999.99"),
        description="Yearly price in USD"
    )
    features: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="Plan features as JSON object"
    )
    max_workspaces: int = Field(
        default=1,
        ge=-1,
        description="Maximum workspaces (-1 = unlimited)"
    )
    max_members_per_workspace: int = Field(
        default=5,
        ge=-1,
        description="Maximum members per workspace (-1 = unlimited)"
    )
    max_topics: int = Field(
        default=100,
        ge=-1,
        description="Maximum topics (-1 = unlimited)"
    )
    max_knowledge_items: int = Field(
        default=1000,
        ge=-1,
        description="Maximum knowledge items (-1 = unlimited)"
    )
    max_api_calls_per_month: int = Field(
        default=10000,
        ge=-1,
        description="Maximum API calls per month (-1 = unlimited)"
    )
    is_active: bool = Field(
        default=True,
        description="Whether the plan is active"
    )
    is_public: bool = Field(
        default=True,
        description="Whether the plan is visible on pricing page"
    )
    lemonsqueezy_product_id: Optional[str] = Field(
        None,
        max_length=255,
        description="LemonSqueezy product ID"
    )
    lemonsqueezy_variant_id_monthly: Optional[str] = Field(
        None,
        max_length=255,
        description="LemonSqueezy variant ID for monthly billing"
    )
    lemonsqueezy_variant_id_yearly: Optional[str] = Field(
        None,
        max_length=255,
        description="LemonSqueezy variant ID for yearly billing"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "startup",
                "display_name": "Startup Plan",
                "description": "Perfect for growing startups",
                "price_monthly": 49.99,
                "price_yearly": 499.99,
                "features": {
                    "collaboration": "Advanced",
                    "support": "Email",
                    "custom_branding": True
                },
                "max_workspaces": 3,
                "max_members_per_workspace": 8,
                "max_topics": 300,
                "max_knowledge_items": 3000,
                "max_api_calls_per_month": 30000,
                "is_active": True,
                "is_public": True
            }
        }
    )


class SubscriptionPlanUpdate(BaseModel):
    """Schema for updating an existing subscription plan (admin only)."""
    display_name: Optional[str] = Field(
        None,
        min_length=2,
        max_length=150,
        description="Human-readable plan name"
    )
    description: Optional[str] = Field(
        None,
        description="Plan description"
    )
    price_monthly: Optional[Decimal] = Field(
        None,
        ge=Decimal("0.00"),
        le=Decimal("99999.99"),
        description="Monthly price in USD"
    )
    price_yearly: Optional[Decimal] = Field(
        None,
        ge=Decimal("0.00"),
        le=Decimal("99999.99"),
        description="Yearly price in USD"
    )
    features: Optional[Dict[str, Any]] = Field(
        None,
        description="Plan features as JSON object"
    )
    max_workspaces: Optional[int] = Field(
        None,
        ge=-1,
        description="Maximum workspaces (-1 = unlimited)"
    )
    max_members_per_workspace: Optional[int] = Field(
        None,
        ge=-1,
        description="Maximum members per workspace (-1 = unlimited)"
    )
    max_topics: Optional[int] = Field(
        None,
        ge=-1,
        description="Maximum topics (-1 = unlimited)"
    )
    max_knowledge_items: Optional[int] = Field(
        None,
        ge=-1,
        description="Maximum knowledge items (-1 = unlimited)"
    )
    max_api_calls_per_month: Optional[int] = Field(
        None,
        ge=-1,
        description="Maximum API calls per month (-1 = unlimited)"
    )
    is_active: Optional[bool] = Field(
        None,
        description="Whether the plan is active"
    )
    is_public: Optional[bool] = Field(
        None,
        description="Whether the plan is visible on pricing page"
    )
    lemonsqueezy_product_id: Optional[str] = Field(
        None,
        max_length=255,
        description="LemonSqueezy product ID"
    )
    lemonsqueezy_variant_id_monthly: Optional[str] = Field(
        None,
        max_length=255,
        description="LemonSqueezy variant ID for monthly billing"
    )
    lemonsqueezy_variant_id_yearly: Optional[str] = Field(
        None,
        max_length=255,
        description="LemonSqueezy variant ID for yearly billing"
    )


class SubscriptionPlanResponse(BaseModel):
    """Schema for subscription plan response."""
    id: str = Field(..., description="Plan UUID")
    name: str = Field(..., description="Plan identifier")
    display_name: str = Field(..., description="Human-readable plan name")
    description: Optional[str] = Field(None, description="Plan description")
    price_monthly: float = Field(..., description="Monthly price in USD")
    price_yearly: float = Field(..., description="Yearly price in USD")
    features: Dict[str, Any] = Field(default_factory=dict, description="Plan features")
    max_workspaces: int = Field(..., description="Maximum workspaces")
    max_members_per_workspace: int = Field(..., description="Maximum members per workspace")
    max_topics: int = Field(..., description="Maximum topics")
    max_knowledge_items: int = Field(..., description="Maximum knowledge items")
    max_api_calls_per_month: int = Field(..., description="Maximum API calls per month")
    is_active: bool = Field(..., description="Whether the plan is active")
    is_public: bool = Field(..., description="Whether the plan is public")
    created_at: str = Field(..., description="Creation timestamp")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "name": "pro",
                "display_name": "Pro Plan",
                "description": "For growing teams",
                "price_monthly": 29.99,
                "price_yearly": 299.99,
                "features": {
                    "collaboration": "Advanced",
                    "support": "Email & Chat"
                },
                "max_workspaces": 5,
                "max_members_per_workspace": 10,
                "max_topics": 500,
                "max_knowledge_items": 5000,
                "max_api_calls_per_month": 50000,
                "is_active": True,
                "is_public": True,
                "created_at": "2025-10-02T18:00:00Z"
            }
        }
    )
