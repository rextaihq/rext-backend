from enum import IntEnum
from typing import Final


class OnboardingStep(IntEnum):
    """Enumeration of onboarding steps."""
    CONTENT_PILLAR = 0
    MARKETING_QUESTIONS = 1
    COMPLETE = 2


# Steps that require specific user actions/input
ACTIONABLE_STEPS: Final[tuple[int, ...]] = (
    OnboardingStep.CONTENT_PILLAR.value,
    OnboardingStep.MARKETING_QUESTIONS.value,
)

# All possible step values including the terminal state
ALL_STEPS: Final[tuple[int, ...]] = (
    OnboardingStep.CONTENT_PILLAR.value,
    OnboardingStep.MARKETING_QUESTIONS.value,
    OnboardingStep.COMPLETE.value,
)

# The last step where a user can perform an action before completion
LAST_ACTIONABLE_STEP: Final[int] = OnboardingStep.MARKETING_QUESTIONS.value
