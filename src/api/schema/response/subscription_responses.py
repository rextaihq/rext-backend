"""
Standardized response schemas for User Subscriptions and Invoices.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.api.schema.response.plan_responses import StageCost


class CreditBonus(BaseModel):
    """An offer's live credit grants, spent first (`bonus_summary`, src/services/credit_grants.py)."""

    label: str
    promotion: Optional[str] = None
    credits: int = Field(description="Credits left in the grants")
    granted: int
    expires_at: Optional[str] = Field(None, description="ISO 8601, the earliest grant's expiry")


class AddedCredits(BaseModel):
    """Credits Rext support added, live (`admin_credit_summary`, src/services/credit_grants.py)."""

    credits: int = Field(description="Credits left of what was added")
    granted: int
    expires_at: Optional[str] = Field(
        None, description="ISO 8601, the soonest expiry; null when none expires"
    )


class RunCost(BaseModel):
    """What one billed button costs against the balance (`run_costs`, src/services/plan_catalog.py)."""

    cost: int
    minimum_balance: int
    can_run: bool
    balance_after: Optional[int] = Field(None, description="Null when the button cannot run")
    stages: List[StageCost]


class CreditBalanceResponse(BaseModel):
    """GET /subscriptions/credits: the balance of the active workspace's owner, or the caller's."""

    current_credits: int = Field(
        description="This month's credits plus the live bonus and added credits"
    )
    monthly_credits: int
    bonus: Optional[CreditBonus] = None
    added_credits: Optional[AddedCredits] = None
    credits_per_month: Optional[int] = Field(None, description="Null for an unlimited plan")
    credits_reset_date: Optional[str] = Field(None, description="ISO 8601")
    articles_remaining: Optional[int] = Field(None, description="Null for an unlimited plan")
    plan_name: Optional[str] = None
    target_user_id: str
    is_workspace_credits: bool
    runs: Dict[str, RunCost] = Field(description="Each billed button, by name")


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
    usage_reset_date: Optional[datetime] = None
    plan_name: Optional[str] = None
    plan_display_name: Optional[str] = None
    plan_features: Optional[Dict[str, Any]] = None
    plan_limits: Optional[Dict[str, Any]] = None
    current_period_end: Optional[str] = None
    customer_portal_url: Optional[str] = None
    current_usage: Optional[Dict[str, Any]] = None

    # Nested arrays for frontend discovery
    plans: List[Any] = Field(default_factory=list, description="Available plans list")


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


class SubscriptionCancelResponse(BaseModel):
    """Response schema for subscription cancellation. Returns the updated subscription dict."""

    id: UUID
    user_id: UUID
    plan_id: UUID
    status: str
    billing_period: str
    cancelled_at: Optional[datetime] = None
    cancellation_reason: Optional[str] = None
    end_date: Optional[datetime] = None
    ends_at: Optional[datetime] = None


class InvoiceItem(BaseModel):
    """Schema for a single invoice item."""

    id: Optional[str] = None
    description: Optional[str] = None
    amount: float
    # Add other fields as identified in manual inspection of provider data


class Invoice(BaseModel):
    """Standardized invoice schema."""

    model_config = ConfigDict(coerce_numbers_to_str=True)

    invoice_id: str
    invoice_number: str
    status: str
    amount: float
    currency: str
    tax: Optional[float] = None
    subtotal: Optional[float] = None
    invoice_url: Optional[str] = None
    invoice_date: Optional[datetime] = None
    due_date: Optional[datetime] = None
    paid_at: Optional[datetime] = None
    customer_email: Optional[str] = None
    customer_name: Optional[str] = None
    items: List[Dict[str, Any]] = Field(default_factory=list)


class InvoiceListResponse(BaseModel):
    """Response schema for invoice list."""

    invoices: List[Invoice]
    count: int


class OrderRow(BaseModel):
    """A single purchase, read from our own orders table."""

    model_config = ConfigDict(coerce_numbers_to_str=True)

    id: str
    lemonsqueezy_order_id: str
    product_name: Optional[str] = None
    status: str
    # Amounts are in cents, as LemonSqueezy reports them.
    total: int
    subtotal: Optional[int] = None
    tax: Optional[int] = None
    currency: str
    receipt_url: Optional[str] = None
    customer_email: Optional[str] = None
    subscription_id: Optional[str] = None
    ordered_at: Optional[datetime] = None
    refunded_at: Optional[datetime] = None
    created_at: datetime

    # Refund-request state, so a billing row can render the right control
    # instead of offering an action the server would refuse.
    refund_request_status: Optional[str] = None
    refund_requested_at: Optional[datetime] = None
    refund_admin_note: Optional[str] = None
    can_request_refund: bool = False
    # Why the refund request is not available, phrased for the customer, or
    # null when it is. Lets the UI explain a missing button instead of just
    # omitting it — the refund window otherwise vanishes silently.
    refund_ineligible_reason: Optional[str] = None

    # Cents refunded against this order and cents still refundable, so the
    # billing row can show what was returned without guessing from the status.
    refunded_amount: int = 0
    refundable_amount: int = 0


class OrderListResponse(BaseModel):
    """Response schema for the user's order history."""

    orders: List[OrderRow]
    count: int


class BillingUrlsResponse(BaseModel):
    """LemonSqueezy's signed billing URLs for a subscription.

    Both are short-lived (~24h), so they are fetched on demand.
    """

    # Frameable — safe to open in the on-site checkout overlay.
    update_payment_method: Optional[str] = None
    # Refuses framing — new tab only, and only needed for tax/billing address.
    customer_portal: Optional[str] = None
