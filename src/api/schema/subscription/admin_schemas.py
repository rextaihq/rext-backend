"""
Admin subscription management schemas.

This module defines Pydantic models for admin subscription operations.
"""

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.api.models.subscription_models.credit_grants import (
    ADMIN_CREDIT_MAX_AMOUNT,
    ADMIN_CREDIT_REASON_MAX_LENGTH,
    ADMIN_CREDIT_REASON_MIN_LENGTH,
)

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


class AdminCreditAdjustment(BaseModel):
    """Body for a super admin adding, deducting or resetting a user's credits.

    add: a grant of ``amount`` credits, lasting unless ``expires_at`` is given.
    deduct: ``amount`` credits, from what admins added first, then from the
    month's credits. reset: the month's credits back to the plan's amount (no
    ``amount``).
    """

    action: Literal["add", "deduct", "reset"]
    amount: Optional[int] = Field(
        None,
        ge=1,
        le=ADMIN_CREDIT_MAX_AMOUNT,
        description="Credits to add or deduct; left out for a reset",
    )
    reason: str = Field(
        ...,
        min_length=ADMIN_CREDIT_REASON_MIN_LENGTH,
        max_length=ADMIN_CREDIT_REASON_MAX_LENGTH,
        description="Why, shown to the customer",
    )
    expires_at: Optional[datetime] = Field(
        None,
        description="When added credits expire (in the future); only for an add. "
        "Left out, they last and are spent after the month's credits.",
    )

    model_config = ConfigDict(
        str_strip_whitespace=True,
        json_schema_extra={
            "example": {
                "action": "add",
                "amount": 150,
                "reason": "Compensation for the outage on 6 October",
            }
        },
    )

    @model_validator(mode="after")
    def _fields_for_the_action(self):
        if self.action == "reset":
            if self.amount is not None:
                raise ValueError("A reset takes no amount")
        elif self.amount is None:
            raise ValueError(f"An amount is required to {self.action} credits")
        if self.expires_at is not None and self.action != "add":
            raise ValueError("Only added credits can expire")
        return self
