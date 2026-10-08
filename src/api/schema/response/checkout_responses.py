"""
Standardized response schemas for Checkout and Usage operations.
"""

from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel


class CheckoutSessionResponse(BaseModel):
    """Response schema for checkout session creation."""

    session_id: str
    checkout_url: str


class UsageMetric(BaseModel):
    """Schema for a single resource's usage metrics."""

    used: int
    limit: Optional[int] = None
    percentage: float
    unlimited: bool


class UsageMetricsResponse(BaseModel):
    """Response schema for detailed resource usage metrics."""

    workspaces: UsageMetric
    members: UsageMetric
    meta: Dict[str, Any]


class ExpiredTrial(BaseModel):
    """A trial that is over with no plan bought since: the state the paywall shows."""

    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None


class BillingAction(BaseModel):
    """What the customer does with a subscription that isn't finished, instead of a new checkout."""

    # "update_payment_method" (a failed renewal) or "resume" (paused, or cancelled before its end)
    action: str
    status: str
    # When the failed renewal's episode began (the date the banner names), and a cancelled plan's end.
    payment_failed_at: Optional[datetime] = None
    ends_at: Optional[datetime] = None


class BillingActionResponse(BaseModel):
    """GET /subscriptions/billing-action: the action, or null when nothing is unfinished."""

    billing_action: Optional[BillingAction] = None


class SubscriptionStatusResponse(BaseModel):
    """Legacy/Legacy-support status response containing subscription, plan, usage, and portal URL."""

    subscription: Optional[Dict[str, Any]] = None
    plan: Optional[Dict[str, Any]] = None
    usage: Any
    portal_url: Optional[str] = None
    # Set when the user's trial is over and nothing replaced it; null otherwise.
    expired_trial: Optional[ExpiredTrial] = None
    # Set when a subscription isn't finished: "update_payment_method" (a failed
    # renewal) or "resume" (paused, or cancelled before its end), with its status.
    # The dashboard offers that action instead of a new checkout; null otherwise.
    billing_action: Optional[BillingAction] = None
