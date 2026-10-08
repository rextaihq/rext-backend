"""Schemas for the incident banner: the one notice every signed-in user sees while something is failing."""

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

#: What a banner may say is affected. A fixed list, so the dashboard words each one itself.
BannerArea = Literal["generation", "keyword_research", "publishing", "billing", "sign_in"]

#: The message is plain text the dashboard shows as text; this keeps it to a line or two.
MESSAGE_MAX_LENGTH = 280
#: A banner always ends: one nobody switched off can't outlive the incident by more than a day.
MIN_MINUTES = 15
MAX_MINUTES = 24 * 60


class IncidentBannerSetRequest(BaseModel):
    """Body for PUT /api/v1/admin/status/banner."""

    message: str = Field(
        ...,
        min_length=1,
        max_length=MESSAGE_MAX_LENGTH,
        description="What is happening, in plain text. Shown as text, never as markup.",
    )
    areas: List[BannerArea] = Field(
        default_factory=list,
        max_length=5,
        description="What is affected; may be empty.",
    )
    duration_minutes: int = Field(
        60,
        ge=MIN_MINUTES,
        le=MAX_MINUTES,
        description="How long the banner shows unless it is switched off first (15 minutes to 24 hours).",
    )

    @field_validator("message")
    @classmethod
    def message_has_words(cls, value: str) -> str:
        text = " ".join(value.split())
        if not text:
            raise ValueError("The message is empty.")
        return text

    @field_validator("areas")
    @classmethod
    def areas_once_each(cls, value: List[str]) -> List[str]:
        return list(dict.fromkeys(value))


class IncidentBannerResponse(BaseModel):
    """The banner as every signed-in user reads it. `active` false means there is none."""

    active: bool
    message: Optional[str] = None
    areas: List[BannerArea] = Field(default_factory=list)
    started_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
