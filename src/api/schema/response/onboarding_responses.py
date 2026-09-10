from typing import Optional

from pydantic import BaseModel

from src.api.schema.onboarding_schemas import OnboardingResponse


class UserOnboardingResponse(OnboardingResponse):
    """Schema for onboarding status response with optional message."""

    message: Optional[str] = None


class ShouldShowOnboardingResponse(BaseModel):
    """Schema for checking if onboarding should be shown."""

    should_show: bool
    message: Optional[str] = None
