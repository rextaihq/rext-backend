"""
Pydantic schemas for the analytics consent endpoints (rext-control task 712).
"""

from typing import Literal, Optional

from pydantic import BaseModel, Field


class UpdateAnalyticsConsentRequest(BaseModel):
    """What the person's browser holds: their answer, and where they were asked from."""

    # Required, and null is a value: "no answer yet". Left out by mistake, it would read as
    # that, so the body has to say it.
    answer: Optional[Literal["granted", "denied"]] = Field(
        ..., description="The person's answer on usage analytics, or null for none yet"
    )
    region: Literal["eea", "other"] = Field(
        ..., description="Where the person was asked from: the EEA asks first, elsewhere doesn't"
    )


class AnalyticsConsentResponse(BaseModel):
    """The stored answer."""

    answer: Optional[Literal["granted", "denied"]] = None
    region: Optional[Literal["eea", "other"]] = None
    answered_at: Optional[str] = None
