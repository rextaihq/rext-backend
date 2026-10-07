"""
Response schemas for the credits a super admin adds, deducts or resets
(src/services/admin_credits.py): the admin's view of a user's credits and
their history, and the customer's own history, which names "Rext support"
and never the admin.
"""

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from src.api.schema.response.subscription_responses import AddedCredits, CreditBonus


class AdminCreditAdjustmentResult(BaseModel):
    """POST /admin/users/{user_id}/credits: what the change did."""

    action: str
    requested_amount: Optional[int] = Field(None, description="Null for a reset")
    amount: int = Field(
        description="Credits added or deducted (less than asked when less was there); "
        "for a reset, the change to the month's credits"
    )
    balance_before: int
    balance_after: int
    monthly_credits: int = Field(description="The month's credits after the change")
    admin_credits: int = Field(description="Credits left of what admins added, after it")
    subscription_id: UUID
    grant_id: Optional[UUID] = Field(None, description="The grant an add made")
    audit_id: UUID


class CreditBreakdown(BaseModel):
    """What a user can spend now, by where it comes from."""

    subscription_id: Optional[UUID] = None
    plan_name: Optional[str] = None
    current_credits: int = Field(description="Everything spendable now")
    monthly_credits: int
    credits_per_month: Optional[int] = None
    credits_reset_date: Optional[str] = Field(None, description="ISO 8601")
    bonus: Optional[CreditBonus] = None
    added_credits: Optional[AddedCredits] = None
    period_adjustment: int = Field(
        description="What admins changed this period's monthly credits by (deductions negative)"
    )


class CreditGrantEntry(BaseModel):
    """Credits an admin added."""

    id: UUID
    amount: int
    remaining: int
    forfeited: int = Field(description="Taken back by a deduction")
    reason: Optional[str] = None
    expires_at: Optional[datetime] = Field(None, description="Null: they last")
    created_at: datetime


class CreditAdjustmentEntry(BaseModel):
    """An admin's change to the credits, from the audit log."""

    id: UUID
    action: Optional[str] = None
    amount: Optional[int] = None
    balance_before: Optional[int] = None
    balance_after: Optional[int] = None
    reason: Optional[str] = None
    expires_at: Optional[str] = Field(None, description="ISO 8601, an add's expiry")
    grant_id: Optional[str] = Field(None, description="The grant an add made, by its id")
    created_at: datetime


class CustomerCreditGrantEntry(CreditGrantEntry):
    granted_by: str = Field(description='Always "Rext support"')


class CustomerCreditAdjustmentEntry(CreditAdjustmentEntry):
    adjusted_by: str = Field(description='Always "Rext support"')


class CreditHistoryResponse(BaseModel):
    """GET /subscriptions/credits/history: the caller's credits changed by Rext support."""

    grants: List[CustomerCreditGrantEntry]
    adjustments: List[CustomerCreditAdjustmentEntry]


class AdminCreditGrantEntry(CreditGrantEntry):
    subscription_id: UUID
    granted_by: Optional[UUID] = Field(None, description="Null once that admin is deleted")
    granted_by_email: Optional[str] = None


class AdminCreditAdjustmentEntry(CreditAdjustmentEntry):
    requested_amount: Optional[int] = None
    adjusted_by: Optional[UUID] = None
    adjusted_by_email: Optional[str] = None


class AdminCreditLimits(BaseModel):
    """What a change may ask for. The dashboard's form reads them from here, so the
    limits are written in one place (the model's constants)."""

    amount_max: int = Field(description="The most credits to add or deduct at once")
    reason_min: int = Field(description="The reason's shortest length, once trimmed")
    reason_max: int = Field(description="The reason's longest length")


class AdminUserCreditsResponse(BaseModel):
    """GET /admin/users/{user_id}/credits: the breakdown and the history, newest first."""

    user_id: UUID
    credits: CreditBreakdown
    limits: AdminCreditLimits
    grants: List[AdminCreditGrantEntry]
    adjustments: List[AdminCreditAdjustmentEntry]
