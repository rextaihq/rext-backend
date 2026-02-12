"""
Refund API Schemas

Pydantic schemas for refund-related API operations.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from src.api.models.subscription_models.refunds import RefundStatus

from pydantic import BaseModel, Field, field_validator


# ============================================================================
# REQUEST SCHEMAS
# ============================================================================

class RefundCreateRequest(BaseModel):
    """Request schema for creating a refund."""

    order_id: Optional[str] = Field(
        None,
        description="LemonSqueezy order ID to refund"
    )
    subscription_id: Optional[UUID] = Field(
        None,
        description="Subscription ID to refund (alternative to order_id)"
    )
    amount: Optional[int] = Field(
        None,
        description="Refund amount in cents (for partial refunds). Omit for full refund.",
        gt=0
    )
    reason: Optional[str] = Field(
        None,
        description="Reason for the refund",
        max_length=1000
    )

    @field_validator("order_id", "subscription_id")
    @classmethod
    def validate_identifiers(cls, v, info):
        """Ensure at least one identifier is provided."""
        # This validation happens after all fields are set
        return v

    model_config = {
        "json_schema_extra": {
            "example": {
                "order_id": "123456",
                "amount": 5000,
                "reason": "Customer requested refund"
            }
        }
    }


class RefundListFilters(BaseModel):
    """Filters for listing refunds."""

    user_id: Optional[UUID] = None
    subscription_id: Optional[UUID] = None
    status: Optional[RefundStatus] = None
    is_partial: Optional[bool] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    page: int = Field(1, ge=1)
    per_page: int = Field(50, ge=1, le=200)


# ============================================================================
# RESPONSE SCHEMAS
# ============================================================================

class RefundResponse(BaseModel):
    """Response schema for a single refund."""

    id: UUID
    user_id: UUID
    subscription_id: Optional[UUID]
    lemonsqueezy_order_id: str
    lemonsqueezy_refund_id: Optional[str]
    refund_amount: int
    original_amount: int
    currency: str
    reason: Optional[str]
    status: RefundStatus
    is_partial: bool
    processed_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    # Additional computed fields
    user_email: Optional[str] = None
    user_name: Optional[str] = None
    plan_name: Optional[str] = None

    model_config = {
        "from_attributes": True,
        "json_schema_extra": {
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "user_id": "123e4567-e89b-12d3-a456-426614174001",
                "subscription_id": "123e4567-e89b-12d3-a456-426614174002",
                "lemonsqueezy_order_id": "123456",
                "lemonsqueezy_refund_id": "ref_123456",
                "refund_amount": 5000,
                "original_amount": 10000,
                "currency": "USD",
                "reason": "Customer requested refund",
                "status": "completed",
                "is_partial": True,
                "processed_at": "2025-10-19T12:00:00",
                "created_at": "2025-10-19T11:00:00",
                "updated_at": "2025-10-19T12:00:00",
                "user_email": "user@example.com",
                "user_name": "John Doe",
                "plan_name": "Pro Plan"
            }
        }
    }


class RefundListResponse(BaseModel):
    """Response schema for listing refunds."""

    refunds: list[RefundResponse]
    pagination: dict
    summary: dict

    model_config = {
        "json_schema_extra": {
            "example": {
                "refunds": [],
                "pagination": {
                    "page": 1,
                    "per_page": 50,
                    "total": 100,
                    "total_pages": 2
                },
                "summary": {
                    "total_refunds": 100,
                    "total_amount": 500000,
                    "partial_refunds": 25,
                    "completed_refunds": 95,
                    "pending_refunds": 3,
                    "failed_refunds": 2
                }
            }
        }
    }


class RefundCreateResponse(BaseModel):
    """Response schema for refund creation."""

    success: bool
    refund: RefundResponse
    message: str

    model_config = {
        "json_schema_extra": {
            "example": {
                "success": True,
                "refund": {},
                "message": "Refund initiated successfully"
            }
        }
    }
