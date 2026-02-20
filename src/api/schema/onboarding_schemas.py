"""Onboarding schemas."""

from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field
from src.constants.onboarding_steps import OnboardingStep



class OnboardingStepUpdate(BaseModel):
    """Schema for updating onboarding step."""

    step: int = Field(
        ...,
        ge=OnboardingStep.STRATEGY.value,
        le=OnboardingStep.COMPLETE.value,
        description="Step number (0-2)",
    )
    action: str = Field(..., description="Action: complete, skip, or set_current")


ONBOARDING_STEPS = [
    {
        "id": OnboardingStep.STRATEGY.value,
        "name": "content_strategy",
        "title": "Welcome to Rext",
        "description": "Choose your content strategy foundation",
        "required": True,
    },
    {
        "id": OnboardingStep.MARKETING.value,
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

    class Config:
        """Pydantic config."""

        from_attributes = True


class OnboardingReset(BaseModel):
    """Schema for resetting onboarding."""

    confirm: bool = Field(..., description="Confirmation to reset onboarding")


# Onboarding step definitions (for frontend reference)
ONBOARDING_STEPS = [
    {
        "id": 0,
        "name": "marketing_questions",
        "title": "Tell Us About Yourself",
        "description": "Help us personalize your experience",
        "required": True,
    },
    {
        "id": 1,
        "name": "complete",
        "title": "You're All Set!",
        "description": "Start creating amazing content",
        "required": True,
    },
]
