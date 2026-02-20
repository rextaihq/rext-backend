from enum import IntEnum


class OnboardingStep(IntEnum):
    STRATEGY = 0
    MARKETING = 1
    COMPLETE = 2


ACTIONABLE_STEPS = [OnboardingStep.STRATEGY.value, OnboardingStep.MARKETING.value]
ALL_STEPS = [
    OnboardingStep.STRATEGY.value,
    OnboardingStep.MARKETING.value,
    OnboardingStep.COMPLETE.value,
]
