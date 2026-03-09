"""
Standardized response schemas for User Subscriptions and Invoices.
"""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime
from uuid import UUID


class SubscriptionDetails(BaseModel):
    """Standardized schema for subscription details."""
    id: UUID
    user_id: UUID
    plan_id: UUID
    status: str
    billing_period: str
    start_date: datetime
    end_date: Optional[datetime] = None
    trial_end_date: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None
    cancellation_reason: Optional[str] = None
    lemonsqueezy_subscription_id: Optional[str] = None
    lemonsqueezy_customer_id: Optional[str] = None
    renews_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None
    current_api_calls: int
    usage_reset_date: Optional[datetime] = None
    plan_name: Optional[str] = None
    plan_display_name: Optional[str] = None
    plan_features: Optional[Dict[str, Any]] = None
    plan_limits: Optional[Dict[str, Any]] = None
    current_period_end: Optional[str] = None
    customer_portal_url: Optional[str] = None
    current_usage: Optional[Dict[str, Any]] = None


class SubscriptionHistoryResponse(BaseModel):
    """Response schema for subscription history."""
    subscriptions: List[Dict[str, Any]]
    count: int


class SubscriptionUpgradeResponse(BaseModel):
    """Response schema for upgrade/downgrade confirmation."""
    id: UUID
    user_id: UUID
    plan_id: UUID
    status: str
    billing_period: str
    plan_name: str
    plan_display_name: str
    # and other fields as needed from to_dict


class InvoiceItem(BaseModel):
    """Schema for a single invoice item."""
    id: Optional[str] = None
    description: Optional[str] = None
    amount: float
    # Add other fields as identified in manual inspection of provider data


class Invoice(BaseModel):
    """Standardized invoice schema."""
    invoice_id: str
    invoice_number: str
    status: str
    amount: float
    currency: str
    tax: Optional[float] = None
    subtotal: Optional[float] = None
    invoice_url: str
    invoice_date: Optional[str] = None
    due_date: Optional[str] = None
    paid_at: Optional[str] = None
    customer_email: Optional[str] = None
    customer_name: Optional[str] = None
    items: List[Dict[str, Any]] = Field(default_factory=list)


class InvoiceListResponse(BaseModel):
    """Response schema for invoice list."""
    invoices: List[Invoice]
    count: int
