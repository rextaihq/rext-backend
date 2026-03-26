from src.constants.onboarding_steps import ACTIONABLE_STEPS, ALL_STEPS, OnboardingStep


def test_actionable_steps_excludes_terminal_complete_step() -> None:
    """Test that ACTIONABLE_STEPS only contains steps requiring user input."""
    assert ACTIONABLE_STEPS == (
        OnboardingStep.CONTENT_PILLAR.value,
        OnboardingStep.MARKETING_QUESTIONS.value,
    )
    assert OnboardingStep.COMPLETE.value not in ACTIONABLE_STEPS


def test_all_steps_contains_everything() -> None:
    """Test that ALL_STEPS contains all enum values."""
    assert set(ALL_STEPS) == {
        OnboardingStep.CONTENT_PILLAR.value,
        OnboardingStep.MARKETING_QUESTIONS.value,
        OnboardingStep.COMPLETE.value,
    }


def test_complete_step_constant_is_stable() -> None:
    """Verify the value of the COMPLETE step is 2."""
    assert OnboardingStep.COMPLETE.value == 2


def test_enum_integrity() -> None:
    """Basic check to ensure enum names match expected values."""
    assert OnboardingStep.CONTENT_PILLAR == 0
    assert OnboardingStep.MARKETING_QUESTIONS == 1
    assert OnboardingStep.COMPLETE == 2
