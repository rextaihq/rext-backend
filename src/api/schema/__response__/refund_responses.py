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
    total: int
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
    refunds: List[RefundAdminRow]
    pagination: RefundPagination
    summary: RefundSummary
    message: Optional[str] = None

class RefundCreateData(BaseModel):
    """Schema for the inner data of a refund creation response."""
    success: bool
    refund: RefundAdminRow
    message: str
