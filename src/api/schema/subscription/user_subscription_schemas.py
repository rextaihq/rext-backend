"""
User subscription schemas for subscription operations.

This module defines Pydantic models for user subscription management.
"""

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from .enums import BillingPeriod, SubscriptionStatus


class SubscriptionUpgradeRequest(BaseModel):
    """Schema for upgrading/downgrading subscription plan."""

    new_plan_id: str = Field(..., description="UUID of the new subscription plan")
    billing_period: Optional[BillingPeriod] = Field(
        None, description="Change billing period (optional)"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "new_plan_id": "123e4567-e89b-12d3-a456-426614174001",
                "billing_period": "yearly",
            }
        }
    )


class SubscriptionCancelRequest(BaseModel):
    """Schema for canceling subscription."""

    reason: Optional[str] = Field(
        None, max_length=500, description="Reason for cancellation (optional)"
    )
    cancel_immediately: bool = Field(
        default=False, description="Cancel immediately or at end of billing period"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {"reason": "Switching to another platform", "cancel_immediately": False}
        }
    )


class UserSubscriptionResponse(BaseModel):
    """Schema for user subscription response."""

    id: str = Field(..., description="Subscription UUID")
    user_id: str = Field(..., description="User UUID")
    plan_id: str = Field(..., description="Plan UUID")
    plan_name: Optional[str] = Field(None, description="Plan name")
    plan_display_name: Optional[str] = Field(None, description="Plan display name")
    status: SubscriptionStatus = Field(..., description="Subscription status")
    billing_period: str = Field(..., description="Billing period")
    start_date: str = Field(..., description="Subscription start date")
    end_date: Optional[str] = Field(None, description="Subscription end date")
    trial_end_date: Optional[str] = Field(None, description="Trial end date")
    cancelled_at: Optional[str] = Field(None, description="Cancellation date")
    cancellation_reason: Optional[str] = Field(None, description="Reason for cancellation")
    created_at: str = Field(..., description="Creation timestamp")

    # LemonSqueezy integration fields
    lemonsqueezy_subscription_id: Optional[str] = Field(
        None, description="LemonSqueezy subscription ID"
    )
    lemonsqueezy_customer_id: Optional[str] = Field(None, description="LemonSqueezy customer ID")
    renews_at: Optional[str] = Field(None, description="Next renewal date")
    ends_at: Optional[str] = Field(None, description="Subscription end date")
    current_period_end: Optional[str] = Field(
        None, description="Current billing period end date (alias for renews_at)"
    )

    model_config = ConfigDict(
        json_schema_extra={
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
                "created_at": "2025-10-01T00:00:00Z",
                "lemonsqueezy_subscription_id": "12345",
                "lemonsqueezy_customer_id": "67890",
                "renews_at": "2025-11-01T00:00:00Z",
                "ends_at": None,
                "current_period_end": "2025-11-01T00:00:00Z",
            }
        }
    )
