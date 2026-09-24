"""
Admin subscription management schemas.

This module defines Pydantic models for admin subscription operations.
"""

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from .enums import BillingPeriod, SubscriptionStatus


class AdminSubscriptionAssignRequest(BaseModel):
    """Schema for admin to manually assign subscription."""

    user_id: str = Field(..., description="User UUID")
    plan_id: str = Field(..., description="Plan UUID")
    billing_period: BillingPeriod = Field(
        default=BillingPeriod.MONTHLY, description="Billing period"
    )
    status: SubscriptionStatus = Field(
        default=SubscriptionStatus.ACTIVE, description="Subscription status"
    )
    trial_days: Optional[int] = Field(
        None, ge=0, le=365, description="Number of trial days (optional)"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "user_id": "123e4567-e89b-12d3-a456-426614174003",
                "plan_id": "123e4567-e89b-12d3-a456-426614174000",
                "billing_period": "yearly",
                "status": "active",
                "trial_days": 30,
            }
        }
    )


class AdminSubscriptionExtendRequest(BaseModel):
    """Schema for admin to extend subscription."""

    extend_days: int = Field(
        ..., ge=1, le=3650, description="Number of days to extend subscription"
    )
    reason: Optional[str] = Field(None, max_length=500, description="Reason for extension")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {"extend_days": 30, "reason": "Compensation for service downtime"}
        }
    )


class AdminUsageResetRequest(BaseModel):
    """Schema for admin to reset usage counter."""

    reset_api_calls: bool = Field(default=True, description="Reset API call counter")
    reason: Optional[str] = Field(None, max_length=500, description="Reason for reset")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "reset_api_calls": True,
                "reason": "Testing completed, reset for production use",
            }
        }
    )
