"""
License validation schemas for LemonSqueezy license key validation.

This module defines Pydantic models for license validation operations.
"""

from pydantic import BaseModel, Field
from typing import Optional, List
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


class LicenseActivateRequest(BaseModel):
    """Schema for activating a license."""
    license_key: str = Field(..., description="License key to activate")
    instance_id: str = Field(..., description="Unique device/instance identifier", max_length=255)
    instance_name: Optional[str] = Field(None, description="Human-readable instance name", max_length=255)

    class Config:
        json_schema_extra = {
            "example": {
                "license_key": "XXXX-XXXX-XXXX-XXXX",
                "instance_id": "device-12345",
                "instance_name": "My Laptop"
            }
        }


class LicenseDeactivateRequest(BaseModel):
    """Schema for deactivating a license activation."""
    instance_id: str = Field(..., description="Instance identifier to deactivate", max_length=255)

    class Config:
        json_schema_extra = {
            "example": {
                "instance_id": "device-12345"
            }
        }


class LicenseActivationResponse(BaseModel):
    """Schema for license activation details."""
    id: str
    license_id: str
    instance_id: str
    instance_name: Optional[str]
    is_active: bool
    activated_at: str
    deactivated_at: Optional[str]

    class Config:
        json_schema_extra = {
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "license_id": "123e4567-e89b-12d3-a456-426614174001",
                "instance_id": "device-12345",
                "instance_name": "My Laptop",
                "is_active": True,
                "activated_at": "2025-10-18T10:30:00Z",
                "deactivated_at": None
            }
        }


class LicenseResponse(BaseModel):
    """Schema for license details."""
    id: str
    license_key: str
    product_name: str
    status: str
    activation_limit: Optional[int]
    activation_count: int
    activated_at: Optional[str]
    expires_at: Optional[str]
    created_at: str

    class Config:
        json_schema_extra = {
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "license_key": "XXXX-XXXX-XXXX-XXXX",
                "product_name": "WREXT Pro License",
                "status": "active",
                "activation_limit": 3,
                "activation_count": 1,
                "activated_at": "2025-10-18T10:30:00Z",
                "expires_at": None,
                "created_at": "2025-10-18T10:00:00Z"
            }
        }


class LicenseListResponse(BaseModel):
    """Schema for list of licenses."""
    licenses: List[LicenseResponse]
    total: int


class LicenseActivationListResponse(BaseModel):
    """Schema for list of license activations."""
    activations: List[LicenseActivationResponse]
    total: int
    active_count: int


class LicenseRevokeRequest(BaseModel):
    """Schema for revoking a license (admin only)."""
    reason: Optional[str] = Field(None, description="Reason for revocation", max_length=500)
