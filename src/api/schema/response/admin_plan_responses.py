"""
Response schemas for a super admin changing a user's plan or extending a trial
(src/services/admin_plan_changes.py): what the admin may choose, with how each
choice is billed and the credits it leaves, and what a change did.
"""

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class AdminPlanSubscription(BaseModel):
    """The subscription whose plan would change."""

    id: UUID
    plan_id: UUID
    plan_name: Optional[str] = None
    plan_display_name: Optional[str] = None
    status: str
    is_trial: bool
    billing_period: Optional[str] = None
    billed_by_provider: bool = Field(description="It has a Lemon Squeezy subscription")
    renews_at: Optional[datetime] = None
    trial_ends_at: Optional[datetime] = None
    monthly_credits: int = Field(description="The month's credits left now")
    credits_per_month: Optional[int] = None


class AdminPlanChangeStanding(BaseModel):
    allowed: bool
    refused_reason: Optional[str] = Field(None, description="Why not, ready to show")
    default_billing: Optional[str] = Field(
        None, description="next_renewal, or not_billed without a Lemon Squeezy subscription"
    )


class AdminTrialExtensionStanding(BaseModel):
    allowed: bool
    refused_reason: Optional[str] = None
    earliest_ends_at: Optional[datetime] = Field(None, description="The new end is after this")
    latest_ends_at: Optional[datetime] = Field(None, description="And no later than this")


class AdminPlanMode(BaseModel):
    """One way a change to this plan and period can be billed."""

    billing: str = Field(description="next_renewal, charge_now or not_billed")
    plan_changes: str = Field(description='When the plan changes: always "now"')
    monthly_credits_after: Optional[int] = Field(
        None, description="The month's credits the change would leave"
    )


class AdminPlanPeriod(BaseModel):
    billing_period: str
    kind: str = Field(description="upgrade, downgrade or period_change")
    allowed: bool
    refused_reason: Optional[str] = None
    modes: List[AdminPlanMode]


class AdminPlanChoice(BaseModel):
    id: UUID
    name: str
    display_name: str
    price_monthly: Optional[str] = Field(None, description='The list price, as "89.00"')
    price_yearly: Optional[str] = None
    credits_per_month: Optional[int] = None
    periods: List[AdminPlanPeriod]


class AdminPlanLimits(BaseModel):
    reason_min: int
    reason_max: int


class AdminUserPlanResponse(BaseModel):
    """GET /admin/users/{user_id}/plan."""

    user_id: UUID
    currency: str = Field(description="The currency of the prices")
    subscription: Optional[AdminPlanSubscription] = None
    change: AdminPlanChangeStanding
    trial_extension: AdminTrialExtensionStanding
    plans: List[AdminPlanChoice]
    limits: AdminPlanLimits


class AdminPlanRef(BaseModel):
    id: UUID
    name: str
    display_name: str


class AdminPlanChangeResult(BaseModel):
    """POST /admin/users/{user_id}/plan."""

    subscription_id: UUID
    old_plan: AdminPlanRef
    new_plan: AdminPlanRef
    old_billing_period: Optional[str] = None
    new_billing_period: str
    billing: str
    monthly_credits_before: int
    monthly_credits_after: int
    renews_at: Optional[datetime] = None
    audit_id: UUID


class AdminTrialExtensionResult(BaseModel):
    """POST /admin/users/{user_id}/trial."""

    subscription_id: UUID
    trial_ended_at_before: Optional[datetime] = None
    trial_ends_at: datetime
    audit_id: UUID
