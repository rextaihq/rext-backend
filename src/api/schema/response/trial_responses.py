"""
Standardized response schemas for Trial operations.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class TrialStatusResponse(BaseModel):
    """Response schema for user-facing trial status."""

    is_trial: bool
    trial_end_date: Optional[datetime] = None
    days_remaining: Optional[int] = None
    trial_expired: bool
