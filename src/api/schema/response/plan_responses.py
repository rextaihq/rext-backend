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


class PlanDeleteResponse(BaseModel):
    """Response schema for plan deletion."""

    deleted_plan_id: UUID
    plan_name: str


# ---------------------------------------------------------------------------
# The public plan catalogue (GET /api/v1/plans). A cap of null is unlimited.
# ---------------------------------------------------------------------------


class CatalogPlan(BaseModel):
    """A plan a customer can buy, with every figure the pricing pages show."""

    name: str
    display_name: str
    description: Optional[str] = None
    price_monthly: float
    price_yearly: float
    price_monthly_billed_yearly: float = Field(description="The yearly price over twelve")
    yearly_saving_percent: Optional[int] = Field(
        None, description="Saving of yearly billing against twelve monthly payments, whole percent"
    )
    credits_per_month: Optional[int] = Field(None, description="Null for a custom amount")
    articles_per_month: Optional[int] = Field(
        None, description="Whole articles a month's credits pay for"
    )
    price_per_article_monthly: Optional[float] = None
    price_per_article_yearly: Optional[float] = None
    max_workspaces: Optional[int] = None
    max_members_per_workspace: Optional[int] = None


class CatalogTrial(BaseModel):
    """The trial every new account starts on."""

    plan_name: str
    days: int
    credits: Optional[int] = None
    articles: Optional[int] = None
    credits_renew: bool
    card_required: bool
    max_workspaces: Optional[int] = None
    max_members_per_workspace: Optional[int] = None


class StageCost(BaseModel):
    """The credits one billed stage of an article takes (src/utils/credit_manager.py)."""

    key: str
    credits: int


class CatalogCredits(BaseModel):
    """What an article costs and the rules around the balance."""

    per_article: int
    stages: List[StageCost]
    keyword_change: int = Field(description="Credits a new keyword takes on top of the article")
    outline_regeneration: int = Field(description="Credits each new outline takes")
    minimum_to_start: int = Field(description="Balance a run needs before its first billed stage")
    low_balance_threshold: int
    carry_over: bool = Field(description="Whether unused credits carry into the next month")


class CatalogOffer(BaseModel):
    """The promotion on subscriptions started now (the `promotions` table)."""

    id: str
    label: str
    kind: str
    credit_multiplier: Optional[int] = None
    bonus_credits: Optional[int] = None
    starts_at: datetime
    ends_at: datetime


class PlanCatalogResponse(BaseModel):
    """The public plan catalogue: plans, the trial, the credit costs and the active offer."""

    currency: str
    plans: List[CatalogPlan]
    trial: Optional[CatalogTrial] = None
    credits: CatalogCredits
    offer: Optional[CatalogOffer] = None
