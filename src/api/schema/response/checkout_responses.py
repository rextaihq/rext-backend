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


class PortalSessionResponse(BaseModel):
    """Response schema for customer portal URL."""

    portal_url: str


class UsageMetric(BaseModel):
    """Schema for a single resource's usage metrics."""

    used: int
    limit: Optional[int] = None
    percentage: float
    unlimited: bool


class APIUsageMetric(UsageMetric):
    """Schema for API usage metrics including reset date."""

    reset_date: Optional[datetime] = None


class UsageMetricsResponse(BaseModel):
    """Response schema for detailed resource usage metrics."""

    workspaces: UsageMetric
    members: UsageMetric
    knowledge_items: UsageMetric
    topics: UsageMetric
    api_calls: APIUsageMetric
    meta: Dict[str, Any]


class ExpiredTrial(BaseModel):
    """A trial that is over with no plan bought since: the state the paywall shows."""

    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None


class SubscriptionStatusResponse(BaseModel):
    """Legacy/Legacy-support status response containing subscription, plan, usage, and portal URL."""

    subscription: Optional[Dict[str, Any]] = None
    plan: Optional[Dict[str, Any]] = None
    usage: Any
    portal_url: Optional[str] = None
    # Set when the user's trial is over and nothing replaced it; null otherwise.
    expired_trial: Optional[ExpiredTrial] = None
