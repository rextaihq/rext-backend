"""
Subscription schemas for request validation and response serialization.

This module defines Pydantic models for subscription-related API operations.
"""

from pydantic import BaseModel, Field, field_validator
from typing import Optional, Dict, Any
from datetime import datetime
from decimal import Decimal
from enum import Enum


class SubscriptionStatus(str, Enum):
    """Subscription status enum."""
    ACTIVE = "active"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    TRIAL = "trial"
    SUSPENDED = "suspended"


class BillingPeriod(str, Enum):
    """Billing period enum."""
    MONTHLY = "monthly"
    YEARLY = "yearly"
    LIFETIME = "lifetime"


# ============================================================================
# SUBSCRIPTION PLAN SCHEMAS (Admin)
# ============================================================================

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
    stripe_price_id_monthly: Optional[str] = Field(
        None,
        max_length=255,
        description="Stripe price ID for monthly billing"
    )
    stripe_price_id_yearly: Optional[str] = Field(
        None,
        max_length=255,
        description="Stripe price ID for yearly billing"
    )

    class Config:
        json_schema_extra = {
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
    stripe_price_id_monthly: Optional[str] = Field(
        None,
        max_length=255,
        description="Stripe price ID for monthly billing"
    )
    stripe_price_id_yearly: Optional[str] = Field(
        None,
        max_length=255,
        description="Stripe price ID for yearly billing"
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

    class Config:
        json_schema_extra = {
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


# ============================================================================
# USER SUBSCRIPTION SCHEMAS
# ============================================================================

class SubscriptionCreateRequest(BaseModel):
    """Schema for user subscribing to a plan."""
    plan_id: str = Field(
        ...,
        description="UUID of the subscription plan"
    )
    billing_period: BillingPeriod = Field(
        default=BillingPeriod.MONTHLY,
        description="Billing period (monthly or yearly)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "plan_id": "123e4567-e89b-12d3-a456-426614174000",
                "billing_period": "monthly"
            }
        }


class SubscriptionUpgradeRequest(BaseModel):
    """Schema for upgrading/downgrading subscription plan."""
    new_plan_id: str = Field(
        ...,
        description="UUID of the new subscription plan"
    )
    billing_period: Optional[BillingPeriod] = Field(
        None,
        description="Change billing period (optional)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "new_plan_id": "123e4567-e89b-12d3-a456-426614174001",
                "billing_period": "yearly"
            }
        }


class SubscriptionCancelRequest(BaseModel):
    """Schema for canceling subscription."""
    reason: Optional[str] = Field(
        None,
        max_length=500,
        description="Reason for cancellation (optional)"
    )
    cancel_immediately: bool = Field(
        default=False,
        description="Cancel immediately or at end of billing period"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "reason": "Switching to another platform",
                "cancel_immediately": False
            }
        }


class UserSubscriptionResponse(BaseModel):
    """Schema for user subscription response."""
    id: str = Field(..., description="Subscription UUID")
    user_id: str = Field(..., description="User UUID")
    plan_id: str = Field(..., description="Plan UUID")
    plan_name: Optional[str] = Field(None, description="Plan name")
    plan_display_name: Optional[str] = Field(None, description="Plan display name")
    status: str = Field(..., description="Subscription status")
    billing_period: str = Field(..., description="Billing period")
    start_date: str = Field(..., description="Subscription start date")
    end_date: Optional[str] = Field(None, description="Subscription end date")
    trial_end_date: Optional[str] = Field(None, description="Trial end date")
    cancelled_at: Optional[str] = Field(None, description="Cancellation date")
    current_api_calls: int = Field(..., description="Current API calls this period")
    created_at: str = Field(..., description="Creation timestamp")

    class Config:
        json_schema_extra = {
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174002",
                "user_id": "123e4567-e89b-12d3-a456-426614174003",
                "plan_id": "123e4567-e89b-12d3-a456-426614174000",
                "plan_name": "pro",
                "plan_display_name": "Pro Plan",
                "status": "active",
                "billing_period": "monthly",
                "start_date": "2025-10-01T00:00:00Z",
                "end_date": None,
                "trial_end_date": "2025-10-15T00:00:00Z",
                "cancelled_at": None,
                "current_api_calls": 2500,
                "created_at": "2025-10-01T00:00:00Z"
            }
        }


# ============================================================================
# USAGE TRACKING SCHEMAS
# ============================================================================

class UsageStatsResponse(BaseModel):
    """Schema for usage statistics response."""
    subscription_id: str = Field(..., description="Subscription UUID")
    plan_name: str = Field(..., description="Current plan name")
    billing_period: str = Field(..., description="Billing period")

    # Current usage
    current_workspaces: int = Field(..., description="Current number of workspaces")
    current_topics: int = Field(..., description="Current number of topics")
    current_knowledge_items: int = Field(..., description="Current number of knowledge items")
    current_api_calls: int = Field(..., description="Current API calls this period")

    # Limits
    max_workspaces: int = Field(..., description="Maximum workspaces allowed")
    max_topics: int = Field(..., description="Maximum topics allowed")
    max_knowledge_items: int = Field(..., description="Maximum knowledge items allowed")
    max_api_calls_per_month: int = Field(..., description="Maximum API calls per month")

    # Usage percentages
    workspaces_usage_percent: float = Field(..., description="Workspaces usage percentage")
    topics_usage_percent: float = Field(..., description="Topics usage percentage")
    knowledge_items_usage_percent: float = Field(..., description="Knowledge items usage percentage")
    api_calls_usage_percent: float = Field(..., description="API calls usage percentage")

    # Reset date
    usage_reset_date: str = Field(..., description="Next usage reset date")

    class Config:
        json_schema_extra = {
            "example": {
                "subscription_id": "123e4567-e89b-12d3-a456-426614174002",
                "plan_name": "pro",
                "billing_period": "monthly",
                "current_workspaces": 3,
                "current_topics": 245,
                "current_knowledge_items": 1820,
                "current_api_calls": 12500,
                "max_workspaces": 5,
                "max_topics": 500,
                "max_knowledge_items": 5000,
                "max_api_calls_per_month": 50000,
                "workspaces_usage_percent": 60.0,
                "topics_usage_percent": 49.0,
                "knowledge_items_usage_percent": 36.4,
                "api_calls_usage_percent": 25.0,
                "usage_reset_date": "2025-11-01T00:00:00Z"
            }
        }


class TrialStatusResponse(BaseModel):
    """Schema for trial status response."""
    is_trial: bool = Field(..., description="Whether subscription is in trial")
    trial_end_date: Optional[str] = Field(None, description="Trial end date")
    days_remaining: Optional[int] = Field(None, description="Days remaining in trial")
    trial_expired: bool = Field(..., description="Whether trial has expired")

    class Config:
        json_schema_extra = {
            "example": {
                "is_trial": True,
                "trial_end_date": "2025-10-15T00:00:00Z",
                "days_remaining": 8,
                "trial_expired": False
            }
        }


# ============================================================================
# ADMIN SUBSCRIPTION MANAGEMENT SCHEMAS
# ============================================================================

class AdminSubscriptionAssignRequest(BaseModel):
    """Schema for admin to manually assign subscription."""
    user_id: str = Field(..., description="User UUID")
    plan_id: str = Field(..., description="Plan UUID")
    billing_period: BillingPeriod = Field(
        default=BillingPeriod.MONTHLY,
        description="Billing period"
    )
    status: SubscriptionStatus = Field(
        default=SubscriptionStatus.ACTIVE,
        description="Subscription status"
    )
    trial_days: Optional[int] = Field(
        None,
        ge=0,
        le=365,
        description="Number of trial days (optional)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "user_id": "123e4567-e89b-12d3-a456-426614174003",
                "plan_id": "123e4567-e89b-12d3-a456-426614174000",
                "billing_period": "yearly",
                "status": "active",
                "trial_days": 30
            }
        }


class AdminSubscriptionExtendRequest(BaseModel):
    """Schema for admin to extend subscription."""
    extend_days: int = Field(
        ...,
        ge=1,
        le=3650,
        description="Number of days to extend subscription"
    )
    reason: Optional[str] = Field(
        None,
        max_length=500,
        description="Reason for extension"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "extend_days": 30,
                "reason": "Compensation for service downtime"
            }
        }


class AdminUsageResetRequest(BaseModel):
    """Schema for admin to reset usage counter."""
    reset_api_calls: bool = Field(
        default=True,
        description="Reset API call counter"
    )
    reason: Optional[str] = Field(
        None,
        max_length=500,
        description="Reason for reset"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "reset_api_calls": True,
                "reason": "Testing completed, reset for production use"
            }
        }


# ============================================================================
# STRIPE INTEGRATION SCHEMAS
# ============================================================================

class CheckoutSessionRequest(BaseModel):
    """Schema for creating Stripe checkout session."""
    plan_id: str = Field(..., description="Plan UUID")
    billing_period: BillingPeriod = Field(..., description="Billing period")
    success_url: str = Field(..., description="URL to redirect after successful payment")
    cancel_url: str = Field(..., description="URL to redirect if payment cancelled")

    class Config:
        json_schema_extra = {
            "example": {
                "plan_id": "123e4567-e89b-12d3-a456-426614174000",
                "billing_period": "monthly",
                "success_url": "https://app.example.com/subscription/success",
                "cancel_url": "https://app.example.com/subscription/cancel"
            }
        }


class CheckoutSessionResponse(BaseModel):
    """Schema for Stripe checkout session response."""
    checkout_url: str = Field(..., description="Stripe checkout URL")
    session_id: str = Field(..., description="Stripe session ID")

    class Config:
        json_schema_extra = {
            "example": {
                "checkout_url": "https://checkout.stripe.com/pay/cs_test_...",
                "session_id": "cs_test_..."
            }
        }


# ============================================================================
# ADMIN ANALYTICS SCHEMAS
# ============================================================================

class SubscriptionStatsResponse(BaseModel):
    """Schema for overall subscription statistics."""
    total_subscriptions: int = Field(..., description="Total subscriptions ever created")
    active_subscriptions: int = Field(..., description="Currently active subscriptions")
    trial_subscriptions: int = Field(..., description="Subscriptions in trial")
    cancelled_subscriptions: int = Field(..., description="Cancelled subscriptions")
    expired_subscriptions: int = Field(..., description="Expired subscriptions")
    suspended_subscriptions: int = Field(..., description="Suspended subscriptions")
    mrr: float = Field(..., description="Monthly Recurring Revenue")
    arr: float = Field(..., description="Annual Recurring Revenue")
    churn_rate_monthly: float = Field(..., description="Monthly churn rate percentage")
    trial_conversion_rate: float = Field(..., description="Trial to paid conversion rate")
    average_ltv: float = Field(..., description="Average customer lifetime value estimate")

    class Config:
        json_schema_extra = {
            "example": {
                "total_subscriptions": 1250,
                "active_subscriptions": 980,
                "trial_subscriptions": 150,
                "cancelled_subscriptions": 120,
                "expired_subscriptions": 0,
                "suspended_subscriptions": 0,
                "mrr": 28420.50,
                "arr": 341046.00,
                "churn_rate_monthly": 2.3,
                "trial_conversion_rate": 68.5,
                "average_ltv": 1245.00
            }
        }


class PlanBreakdown(BaseModel):
    """Schema for subscription breakdown by plan."""
    plan_id: str
    plan_name: str
    plan_display_name: str
    subscription_count: int
    revenue_monthly: float
    revenue_yearly: float

    class Config:
        json_schema_extra = {
            "example": {
                "plan_id": "123e4567-e89b-12d3-a456-426614174000",
                "plan_name": "pro",
                "plan_display_name": "Pro Plan",
                "subscription_count": 420,
                "revenue_monthly": 12579.80,
                "revenue_yearly": 150957.60
            }
        }


class RevenueMetricsResponse(BaseModel):
    """Schema for revenue metrics and breakdown."""
    current_month: Dict[str, float] = Field(..., description="Current month revenue breakdown")
    by_plan: List[PlanBreakdown] = Field(..., description="Revenue breakdown by plan")
    growth_rate: float = Field(..., description="Month-over-month growth rate")

    class Config:
        json_schema_extra = {
            "example": {
                "current_month": {
                    "mrr": 28420.50,
                    "new_revenue": 5240.00,
                    "expansion_revenue": 1850.00,
                    "contraction_revenue": -450.00,
                    "churned_revenue": -1220.00
                },
                "by_plan": [
                    {
                        "plan_id": "123e4567-e89b-12d3-a456-426614174000",
                        "plan_name": "pro",
                        "plan_display_name": "Pro Plan",
                        "subscription_count": 420,
                        "revenue_monthly": 12579.80,
                        "revenue_yearly": 150957.60
                    }
                ],
                "growth_rate": 12.5
            }
        }


class ChurnAnalysisResponse(BaseModel):
    """Schema for churn analysis."""
    period: str = Field(..., description="Analysis period")
    total_active_start: int = Field(..., description="Active subscriptions at start")
    new_subscriptions: int = Field(..., description="New subscriptions in period")
    cancellations: int = Field(..., description="Cancellations in period")
    total_active_end: int = Field(..., description="Active subscriptions at end")
    churn_rate: float = Field(..., description="Churn rate percentage")
    retention_rate: float = Field(..., description="Retention rate percentage")

    class Config:
        json_schema_extra = {
            "example": {
                "period": "last_30_days",
                "total_active_start": 1000,
                "new_subscriptions": 50,
                "cancellations": 23,
                "total_active_end": 1027,
                "churn_rate": 2.3,
                "retention_rate": 97.7
            }
        }


class TrialConversionResponse(BaseModel):
    """Schema for trial conversion metrics."""
    total_trials_started: int = Field(..., description="Total trials started in period")
    trials_converted: int = Field(..., description="Trials converted to paid")
    trials_expired: int = Field(..., description="Trials that expired")
    trials_active: int = Field(..., description="Trials still active")
    conversion_rate: float = Field(..., description="Conversion rate percentage")
    average_trial_length_days: float = Field(..., description="Average trial duration")

    class Config:
        json_schema_extra = {
            "example": {
                "total_trials_started": 200,
                "trials_converted": 137,
                "trials_expired": 45,
                "trials_active": 18,
                "conversion_rate": 68.5,
                "average_trial_length_days": 13.2
            }
        }
