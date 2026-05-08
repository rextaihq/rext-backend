# from typing import List, Optional
# from pydantic import Field
# from src.flow.model.structure.outlines.base import BaseOutline, Section


# class FeatureOverviewOutline(BaseOutline):
#     """Outline for a page describing the features of a product."""
#     product_name: str = Field(description="The product these features belong to.")
#     number_of_features_highlighted: int = Field(description="How many major features are discussed.")
#     target_user_role: Optional[str] = Field(description="Who these features are built for (e.g., 'Developers', 'Marketers').")
#     integration_mentions: Optional[List[str]] = Field(description="Any third-party integrations mentioned along with these features.")

from typing import List, Optional, Literal
from pydantic import BaseModel, Field


# -------------------------
# HERO (FEATURE CLARITY)
# -------------------------

class FeatureHero(BaseModel):
    feature_name: str
    headline: str = Field(description="Clear outcome-based statement of the feature")
    subheadline: str = Field(description="Explains value + use case in simple terms")

    primary_cta: str = Field(description="e.g., 'Try Feature', 'Explore Now', 'Enable Feature'")
    secondary_cta: Optional[str] = None

    demo_available: Optional[bool] = True


# -------------------------
# WHAT IT DOES (CORE FUNCTIONALITY)
# -------------------------

class FeatureFunction(BaseModel):
    what_it_does: str
    how_it_works_summary: str


# -------------------------
# KEY BENEFITS (OUTCOME-FIRST MODEL)
# -------------------------

class FeatureBenefit(BaseModel):
    benefit: str
    explanation: str


class FeatureBenefits(BaseModel):
    benefits: List[FeatureBenefit]


# -------------------------
# USE CASES (REAL-WORLD CONTEXT)
# -------------------------

class UseCase(BaseModel):
    scenario: str
    outcome: str


class UseCases(BaseModel):
    cases: List[UseCase]


# -------------------------
# HOW IT WORKS (SIMPLIFIED FLOW)
# -------------------------

class Step(BaseModel):
    step: str
    description: str


class HowItWorks(BaseModel):
    steps: List[Step]


# -------------------------
# INTEGRATIONS (2026 SaaS EXPECTATION)
# -------------------------

class Integration(BaseModel):
    name: str
    description: Optional[str]
    link: Optional[str]


class Integrations(BaseModel):
    tools: List[Integration]


# -------------------------
# PREREQUISITES (REDUCES FRICTION)
# -------------------------

class Prerequisites(BaseModel):
    requirements: List[str]
    availability: Optional[str] = Field(
        default=None,
        description="Plan or tier availability (Free, Pro, Enterprise)"
    )


# -------------------------
# COMPARISON (OPTIONAL BUT POWERFUL)
# -------------------------

class FeatureComparison(BaseModel):
    compared_to: str
    advantage: str
    difference_points: List[str]


# -------------------------
# SOCIAL PROOF (ADOPTION SIGNALS)
# -------------------------

class SocialProof(BaseModel):
    usage_metrics: List[str]
    testimonials: Optional[List[str]] = Field(default_factory=list)
    case_studies: Optional[List[str]] = Field(default_factory=list)


# -------------------------
# TROUBLESHOOTING (LIGHTWEIGHT)
# -------------------------

class CommonIssue(BaseModel):
    issue: str
    solution: str


class Troubleshooting(BaseModel):
    issues: List[CommonIssue]


# -------------------------
# CTA (FEATURE ACTIVATION FOCUS)
# -------------------------

class CTASection(BaseModel):
    primary_cta: str
    secondary_cta: Optional[str] = None
    activation_hint: Optional[str] = Field(
        default=None,
        description="Encourages first use (e.g., 'Takes less than 2 minutes')"
    )


# -------------------------
# FINAL FEATURE OVERVIEW SCHEMA
# -------------------------

class FeatureOverviewOutline(BaseModel):
    # Core metadata
    title: str
    slug_suggestion: str = Field(pattern=r"^[a-z0-9-]+$")
    focus_keyphrase: str
    keywords_to_include: List[str] = Field(
        default_factory=list,
        description="Secondary and long-tail keywords to naturally incorporate throughout the page."
    )

    target_audience: List[str]
    tone: Literal[
        "Clear", "Educational", "Conversational",
        "Professional", "Product-focused", "Action-oriented"
    ]

    # Core Feature Structure (activation flow)
    hero: FeatureHero
    function: FeatureFunction
    benefits: FeatureBenefits
    use_cases: UseCases
    how_it_works: HowItWorks

    # Adoption accelerators
    integrations: Optional[Integrations]
    prerequisites: Optional[Prerequisites]
    comparison: Optional[FeatureComparison]

    # Trust layer
    social_proof: SocialProof
    troubleshooting: Optional[Troubleshooting]

    # CTA system (activation-focused)
    cta: CTASection

    # Optimization Layer (2026 PLG standard)
    activation_goal: str = Field(
        description="What user achieves after using feature first time"
    )

    time_to_first_value_seconds: Optional[int] = Field(
        default=120,
        description="Time for user to experience feature value"
    )

    feature_adoption_stage: Literal[
        "discovery",
        "activation",
        "retention",
        "expansion"
    ]

    target_word_count: int = Field(
        default=800,
        ge=400,
        le=2500,
        description="Feature pages are medium-length activation pages"
    )