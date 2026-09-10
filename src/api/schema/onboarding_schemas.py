"""Onboarding schemas."""

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.constants.onboarding_steps import ALL_STEPS, OnboardingStep


class OnboardingStepUpdate(BaseModel):
    """Schema for updating onboarding step."""

    step: int = Field(
        ...,
        ge=min(ALL_STEPS),
        le=max(ALL_STEPS),
        description=f"Step number ({min(ALL_STEPS)}-{max(ALL_STEPS)})",
    )
    action: str = Field(..., description="Action: complete, skip, or set_current")


ONBOARDING_STEPS = [
    {
        "id": OnboardingStep.CONTENT_PILLAR.value,
        "name": "content_pillar",
        "title": "Welcome to Rext",
        "description": "Choose your content pillars foundation",
        "required": True,
    },
    {
        "id": OnboardingStep.MARKETING_QUESTIONS.value,
        "name": "marketing_questions",
        "title": "Tell Us About Yourself",
        "description": "Help us personalize your experience",
        "required": True,
    },
    {
        "id": OnboardingStep.COMPLETE.value,
        "name": "complete",
        "title": "You're All Set!",
        "description": "Start creating amazing content",
        "required": True,
    },
]


class OnboardingMarketingData(BaseModel):
    """Schema for marketing data collected during onboarding."""

    user_industry: Optional[str] = Field(None, max_length=100, description="User's industry")
    user_role: Optional[str] = Field(None, max_length=100, description="User's role")
    user_goal: Optional[str] = Field(None, description="User's primary goal")
    heard_from: Optional[str] = Field(None, max_length=100, description="How user heard about us")


class OnboardingResponse(BaseModel):
    """Schema for onboarding status response."""

    id: UUID
    user_id: UUID
    completed: bool
    current_step: int
    completed_steps: List[int]
    skipped_steps: List[int]

    # Marketing data
    user_industry: Optional[str]
    user_role: Optional[str]
    user_goal: Optional[str]
    heard_from: Optional[str]

    # Timestamps
    started_at: datetime
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class OnboardingReset(BaseModel):
    """Schema for resetting onboarding."""

    confirm: bool = Field(..., description="Confirmation to reset onboarding")
