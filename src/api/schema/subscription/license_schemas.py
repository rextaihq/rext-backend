"""
License validation schemas for LemonSqueezy license key validation.

This module defines Pydantic models for license validation operations.
"""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class LicenseValidateRequest(BaseModel):
    """Schema for license validation request."""
    license_key: str = Field(
        ...,
        description="License key to validate",
        min_length=1
    )
    instance_id: Optional[str] = Field(
        None,
        description="Optional device/instance identifier for activation tracking"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "license_key": "ABCD-1234-EFGH-5678",
                "instance_id": "device-uuid-123"
            }
        }


class LicenseValidateResponse(BaseModel):
    """Schema for license validation response."""
    valid: bool = Field(..., description="Whether the license is valid")
    license_key: str = Field(..., description="License key that was validated")
    status: str = Field(..., description="License status (active, inactive, expired, etc.)")
    activated: bool = Field(..., description="Whether license is activated")
    activation_limit: Optional[int] = Field(None, description="Maximum number of activations allowed")
    activation_usage: Optional[int] = Field(None, description="Current number of activations")
    expires_at: Optional[str] = Field(None, description="Expiration date (ISO format)")
    customer_email: Optional[str] = Field(None, description="Customer email associated with license")
    customer_name: Optional[str] = Field(None, description="Customer name")
    product_name: Optional[str] = Field(None, description="Product/plan name")
    variant_name: Optional[str] = Field(None, description="Variant name")

    class Config:
        json_schema_extra = {
            "example": {
                "valid": True,
                "license_key": "ABCD-1234-EFGH-5678",
                "status": "active",
                "activated": True,
                "activation_limit": 5,
                "activation_usage": 2,
                "expires_at": None,
                "customer_email": "user@example.com",
                "customer_name": "John Doe",
                "product_name": "Lifetime Pro Plan",
                "variant_name": "Lifetime"
            }
        }
