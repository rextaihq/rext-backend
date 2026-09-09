# from typing import List, Optional
# from pydantic import Field
# from src.flow.model.structure.outlines.base import BaseOutline, Section


# class SignupPageOutline(BaseOutline):
#     """Outline for a signup or registration page."""
#     platform_name: str = Field(description="What the user is signing up for.")
#     value_prop_reminder: str = Field(description="Short text reminding them WHY they should sign up.")
#     social_login_options: Optional[List[str]] = Field(description="E.g., 'Google', 'GitHub'.")
#     required_fields: List[str] = Field(description="E.g., 'Email', 'Password', 'Company Name'.")


from typing import List, Literal, Optional

from pydantic import BaseModel, Field

# -------------------------
# HERO / VALUE PROPOSITION
# -------------------------


class SignupHero(BaseModel):
    headline: str = Field(description="Clear benefit-driven hook (what user gets immediately)")
    subheadline: str = Field(description="Explains outcome + reduces uncertainty")

    primary_cta: str = Field(description="e.g., 'Create Free Account', 'Get Started'")
    secondary_cta: Optional[str] = None

    trust_signals: Optional[List[str]] = Field(
        default_factory=list, description="Security badges, user counts, reviews, logos"
    )


# -------------------------
# VALUE STACK (WHY SIGN UP)
# -------------------------


class ValueStack(BaseModel):
    benefits: List[str] = Field(description="Core user outcomes after signup")
    time_to_value: Optional[str] = Field(
        default=None, description="How fast user gets benefit (e.g., 'Under 2 minutes')"
    )
    unique_value: Optional[str] = Field(default=None, description="Why this product is different")


# -------------------------
# SIGNUP FLOW
# -------------------------


class SignupField(BaseModel):
    field_name: str
    field_type: Literal["text", "email", "password", "number", "checkbox", "dropdown", "phone"]
    required: bool
    placeholder: Optional[str] = None


class SignupForm(BaseModel):
    fields: List[SignupField]
    social_signup_options: Optional[List[str]] = Field(
        default_factory=list, description="Google, Apple, GitHub, etc."
    )
    passwordless: Optional[bool] = False


# -------------------------
# FRICITON REDUCTION STRATEGY
# -------------------------


class FrictionReduction(BaseModel):
    minimal_fields: bool
    auto_fill_support: Optional[bool] = True
    progress_indicator: Optional[bool] = False
    guest_mode_available: Optional[bool] = False


# -------------------------
# ONBOARDING EXPECTATION
# -------------------------


class PostSignupExperience(BaseModel):
    onboarding_steps: List[str]
    first_action: str = Field(description="What user does immediately after signup")
    activation_goal: str = Field(description="Aha moment definition")


# -------------------------
# TRUST + SECURITY
# -------------------------


class TrustLayer(BaseModel):
    security_claims: List[str] = Field(description="SSL, encryption, GDPR compliance, etc.")
    privacy_statement: Optional[str]
    testimonials: Optional[List[str]] = Field(default_factory=list)


# -------------------------
# OBJECTION HANDLING
# -------------------------


class Objection(BaseModel):
    concern: str
    response: str


class ObjectionHandling(BaseModel):
    objections: List[Objection]


# -------------------------
# CTA SYSTEM
# -------------------------


class CTASection(BaseModel):
    primary_cta: str
    secondary_cta: Optional[str] = None
    reassurance_text: Optional[str] = Field(
        default=None, description="e.g., 'No credit card required', 'Cancel anytime'"
    )


# -------------------------
# FINAL SIGNUP PAGE SCHEMA
# -------------------------


class SignupPageOutline(BaseModel):
    # Core metadata
    title: str
    slug_suggestion: str = Field(pattern=r"^[a-z0-9-]+$")
    focus_keyphrase: str
    keywords_to_include: List[str] = Field(
        default_factory=list,
        description="Secondary and long-tail keywords to naturally incorporate throughout the page.",
    )

    target_audience: List[str]
    tone: Literal[
        "Friendly", "Trustworthy", "Conversational", "Direct", "Action-oriented", "Reassuring"
    ]

    # Conversion Goal
    conversion_goal: Literal[
        "create_account", "start_free_trial", "join_waitlist", "access_platform"
    ]

    # Page Structure (Conversion Flow)
    hero: SignupHero
    value_stack: ValueStack
    signup_form: SignupForm
    friction_reduction: FrictionReduction
    onboarding: PostSignupExperience

    # Trust Layer
    trust: TrustLayer
    objection_handling: ObjectionHandling

    # CTA Layer
    cta: CTASection

    # Optimization Layer (2026 PLG standard)
    signup_strategy_type: Literal[
        "instant_access", "email_required", "social_login_first", "passwordless", "invite_only"
    ]

    activation_metric: Optional[str] = Field(
        default=None, description="Key activation event (e.g., 'first project created')"
    )

    target_time_to_signup_seconds: Optional[int] = Field(
        default=120, description="Ideal time-to-signup for optimization"
    )

    target_word_count: int = Field(
        default=400, ge=200, le=1500, description="Signup pages are ultra-lightweight"
    )
