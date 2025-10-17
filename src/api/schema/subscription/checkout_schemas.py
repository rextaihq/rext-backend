"""
Payment checkout schemas for payment processing.

This module defines Pydantic models for payment checkout operations.
"""

from pydantic import BaseModel, Field
from .enums import BillingPeriod


class CheckoutSessionRequest(BaseModel):
    """Schema for creating payment checkout session."""
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
    """Schema for payment checkout session response."""
    checkout_url: str = Field(..., description="Payment checkout URL")
    session_id: str = Field(..., description="Checkout session ID")

    class Config:
        json_schema_extra = {
            "example": {
                "checkout_url": "https://checkout.lemonsqueezy.com/...",
                "session_id": "abc123..."
            }
        }
