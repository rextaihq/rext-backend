"""Administrative subscription response schemas."""

from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime

class UserSubscriptionBase(BaseModel):
    """Base schema for user subscription data."""
    id: str
    user_id: str
    plan_id: str
    status: str
    billing_period: str
    start_date: str
    end_date: Optional[str] = None
    trial_end_date: Optional[str] = None
    cancelled_at: Optional[str] = None
    cancellation_reason: Optional[str] = None
    lemonsqueezy_subscription_id: Optional[str] = None
    lemonsqueezy_customer_id: Optional[str] = None
    lemonsqueezy_order_id: Optional[str] = None
    lemonsqueezy_product_id: Optional[str] = None
    lemonsqueezy_variant_id: Optional[str] = None
    renews_at: Optional[str] = None
    ends_at: Optional[str] = None
    cancel_at_period_end: bool
    grace_period_end: Optional[str] = None
    payment_failed_at: Optional[str] = None
    current_api_calls: int
    usage_reset_date: str
    created_at: str
    updated_at: str

class SubscriptionAdminRow(UserSubscriptionBase):
    """Schema for a single row in the subscription list."""
    user_email: str
    user_full_name: str
    plan_name: str
    plan_display_name: str

class SubscriptionAdminListResponse(BaseModel):
    """Schema for the subscription list response data."""
    subscriptions: List[SubscriptionAdminRow]
    total: int
    limit: int
    offset: int
    has_more: bool
    message: Optional[str] = None

class AdminUserSummary(BaseModel):
    """Summary of a user for admin views."""
    id: str
    email: str
    full_name: str
    status: str

class SubscriptionPlanAdminResponse(BaseModel):
    """Schema for subscription plan data in admin views."""
    id: str
    name: str
    display_name: str
    description: Optional[str] = None
    price_monthly: float
    price_yearly: float
    features: Dict[str, Any]
    max_workspaces: int
    max_members_per_workspace: int
    max_topics: int
    max_knowledge_items: int
    max_api_calls_per_month: int
    is_active: bool
    is_public: bool
    provider_price_id_monthly: Optional[str] = None
    provider_price_id_yearly: Optional[str] = None
    lemonsqueezy_product_id: Optional[str] = None
    lemonsqueezy_variant_id_monthly: Optional[str] = None
    lemonsqueezy_variant_id_yearly: Optional[str] = None
    lemonsqueezy_store_id: Optional[str] = None
    created_at: str
    updated_at: str

class SubscriptionAdminAssignResponse(UserSubscriptionBase):
    """Schema for the subscription assignment response data."""
    plan_name: str
    plan_display_name: str
    user_full_name: str
    user_email_masked: str
    message: Optional[str] = None

class SubscriptionAdminDetailResponse(UserSubscriptionBase):
    """Schema for the subscription detail response data."""
    user: AdminUserSummary
    plan: SubscriptionPlanAdminResponse
    message: Optional[str] = None
