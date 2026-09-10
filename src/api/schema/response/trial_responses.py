"""
Standardized response schemas for Trial operations.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class TrialEligibilityResponse(BaseModel):
    """Response schema for trial eligibility checks."""

    eligible: bool
    has_active_trial: bool
    has_previous_trial: bool
    previous_trials_count: int
    reason: Optional[str] = None


class TrialExtensionResponse(BaseModel):
    """Response schema for admin trial extensions."""

    id: UUID
    user_id: UUID
    status: str
    trial_end_date: Optional[datetime] = None
    extension_days: int
    extended_by: UUID
    extension_reason: Optional[str] = None
    trial_extensions: List[Dict[str, Any]] = Field(default_factory=list)


class TrialAnalyticsResponse(BaseModel):
    """Response schema for trial conversion analytics."""

    total_conversions: int
    average_trial_duration: float
    average_conversion_time: float
    total_revenue: float
    conversion_by_period: Dict[str, int]
    date_range: Dict[str, Optional[str]]


class ExpiringTrial(BaseModel):
    """Schema for a single expiring trial item."""

    id: UUID
    user_id: UUID
    plan_id: UUID
    status: str
    trial_end_date: Optional[datetime] = None
    created_at: datetime


class ExpiringTrialsResponse(BaseModel):
    """Response schema for listing expiring trials."""

    trials: List[ExpiringTrial]
    total: int
    days_until_expiry: int


class TrialStatusResponse(BaseModel):
    """Response schema for user-facing trial status."""

    is_trial: bool
    trial_end_date: Optional[datetime] = None
    days_remaining: Optional[int] = None
    trial_expired: bool
