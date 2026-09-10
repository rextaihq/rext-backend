"""
Standardized response schemas for Subscription Plans.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class PlanDetails(BaseModel):
    """Detailed information about a subscription plan."""

    id: UUID
    name: str
    display_name: str
    description: Optional[str] = None
    price_monthly: float
    price_yearly: float
    features: Dict[str, Any] = Field(default_factory=dict)
    max_workspaces: int
    max_members_per_workspace: int
    max_topics: int
    max_knowledge_items: int
    max_api_calls_per_month: int
    is_active: bool
    is_public: bool
    lemonsqueezy_product_id: Optional[str] = None
    lemonsqueezy_variant_id_monthly: Optional[str] = None
    lemonsqueezy_variant_id_yearly: Optional[str] = None
    lemonsqueezy_store_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    active_subscriptions: Optional[int] = None


class PlanListResponse(BaseModel):
    """Response schema for listing plans."""

    plans: List[PlanDetails]
    count: int


class PlanCreateResponse(BaseModel):
    """Response schema for plan creation."""

    plan: PlanDetails
    message: str


class PlanDeleteResponse(BaseModel):
    """Response schema for plan deletion."""

    deleted_plan_id: UUID
    plan_name: str
