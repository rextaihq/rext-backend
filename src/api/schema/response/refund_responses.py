"""Refund response schemas for admin domain."""

from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
from uuid import UUID
from src.api.models.subscription_models.refunds import RefundStatus

class RefundAdminRow(BaseModel):
    """Schema for a single refund record in a list or detail view."""
    id: UUID
    user_id: UUID
    subscription_id: Optional[UUID] = None
    lemonsqueezy_order_id: str
    lemonsqueezy_refund_id: Optional[str] = None
    refund_amount: int
    original_amount: int
    currency: str
    reason: Optional[str] = None
    status: RefundStatus
    is_partial: bool
    processed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    
    # Extended fields from service layer
    user_email_masked: Optional[str] = None
    user_name: Optional[str] = None
    plan_name: Optional[str] = None
    message: Optional[str] = None

class RefundPagination(BaseModel):
    """Schema for refund pagination metadata."""
    page: int
    per_page: int
    total_items: int
    total_pages: int

class RefundSummary(BaseModel):
    """Schema for refund summary statistics."""
    total_refunds: int
    total_amount: int
    partial_refunds: int
    completed_refunds: int
    pending_refunds: int
    failed_refunds: int

class RefundAdminListResponse(BaseModel):
    """Schema for the refund list response data."""
    data: List[RefundAdminRow]
    pagination: RefundPagination
    summary: RefundSummary
    message: Optional[str] = None

class RefundCreateData(BaseModel):
    """Schema for the inner data of a refund creation response."""
    success: bool
    refund: RefundAdminRow
    message: str


# Aliases for non-admin contexts
RefundResponse = RefundAdminRow
RefundListResponse = RefundAdminListResponse


class RefundableOrderRow(BaseModel):
    """An order an admin can pick to refund against.

    Sourced from our local `orders` table, so the LemonSqueezy order id it
    carries is guaranteed to resolve when a refund is created against it.
    """
    id: UUID
    lemonsqueezy_order_id: str
    user_id: UUID
    user_email: Optional[str] = None
    user_name: Optional[str] = None
    subscription_id: Optional[UUID] = None
    product_name: Optional[str] = None
    status: str
    # Cents, matching LemonSqueezy and the refunds table.
    total: int
    currency: str
    receipt_url: Optional[str] = None
    ordered_at: Optional[datetime] = None
    created_at: datetime

    # True only when nothing is left to refund. A partially refunded order is
    # still refundable for its balance, so it stays selectable.
    already_refunded: bool = False
    # Cents refunded so far, and cents still refundable. Both computed
    # server-side so the UI never re-derives them from what it happens to have.
    refunded_amount: int = 0
    refundable_amount: int = 0


class RefundableOrderListResponse(BaseModel):
    """Schema for the refundable-order search response."""
    data: List[RefundableOrderRow]
    pagination: RefundPagination


class RefundRequestRow(BaseModel):
    """A customer refund request, for both the user and admin views."""
    id: UUID
    user_id: UUID
    order_id: UUID
    lemonsqueezy_order_id: str
    requested_amount: int
    currency: str
    reason: str
    status: str
    admin_note: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    refund_id: Optional[UUID] = None
    created_at: datetime

    # Context joined in for the admin queue.
    user_email: Optional[str] = None
    user_name: Optional[str] = None
    product_name: Optional[str] = None
    order_total: Optional[int] = None

    # The order's money state, so the queue can show what an approval is worth
    # and whether it has actually been paid out yet.
    refunded_amount: int = 0
    refundable_amount: int = 0
    # Approved, but no refund issued against it yet. Drives "Process refund".
    awaiting_processing: bool = False


class RefundRequestListResponse(BaseModel):
    """Schema for a list of refund requests."""
    data: List[RefundRequestRow]
    pagination: Optional[RefundPagination] = None
