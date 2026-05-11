# from typing import List, Optional
# from pydantic import Field
# from src.flow.model.structure.outlines.base import BaseOutline, Section


# class ReviewSection(Section):
#     """Specific for product review focus."""
#     product_feature: str = Field(description="The specific feature being reviewed in this section.")
#     rating: Optional[float] = Field(description="Rating for this particular feature (0.0 to 10.0).")


# class InDepthReviewOutline(BaseOutline):
#     """Outline for a single-product in-depth review."""
#     product_name: str = Field(description="The name of the product or service.")
#     manufacturer: Optional[str] = Field(description="Product manufacturer or developer.")
#     is_biased: bool = Field(default=False, description="Whether the review is promotional or independent.")
#     verdict: Optional[str] = Field(description="The final verdict on the product.")
#     sections: List[ReviewSection] = Field(description="Detailed feature-by-feature review sections.")
#     overall_rating: float = Field(ge=0.0, le=10.0, description="The overall numerical rating out of 10.")


from typing import List, Optional, Literal
from pydantic import BaseModel, Field


# -------------------------
# HERO / REVIEW POSITIONING
# -------------------------

class ReviewHero(BaseModel):
    product_name: str
    headline: str = Field(description="Clear evaluation statement (e.g., 'Is X worth it in 2026?')")
    subheadline: str = Field(description="Explains scope: who this review is for")

    primary_cta: str = Field(default="Try Product")
    secondary_cta: Optional[str] = Field(default="Compare Alternatives")

    verdict_preview: Optional[str] = Field(
        default=None,
        description="Quick summary verdict (e.g., 'Recommended / Not Recommended / Conditional')"
    )


# -------------------------
# REVIEW CONTEXT (CRITICAL TRUST LAYER)
# -------------------------

class ReviewContext(BaseModel):
    evaluation_purpose: List[str]
    testing_methodology: Optional[str]
    review_depth_level: Literal["light", "standard", "deep"] = "deep"
    update_frequency: Optional[str]


# -------------------------
# PRODUCT OVERVIEW
# -------------------------

class ProductOverview(BaseModel):
    what_it_is: str
    who_it_is_for: List[str]
    core_value_proposition: str


# -------------------------
# FEATURE DEEP DIVE (CORE OF IN-DEPTH REVIEW)
# -------------------------

class FeatureEvaluation(BaseModel):
    feature_name: str
    real_world_usage: str
    strengths: List[str]
    limitations: List[str]
    performance_notes: Optional[str]


class FeatureSection(BaseModel):
    features: List[FeatureEvaluation]


# -------------------------
# USABILITY & UX ANALYSIS
# -------------------------

class UsabilityAnalysis(BaseModel):
    onboarding_experience: str
    interface_quality: str
    learning_curve: Literal["easy", "medium", "hard"]
    workflow_efficiency: str


# -------------------------
# PERFORMANCE & RELIABILITY
# -------------------------

class PerformanceMetrics(BaseModel):
    speed: Optional[str]
    uptime: Optional[str]
    scalability: Optional[str]
    stability_notes: Optional[str]


# -------------------------
# PRICING EVALUATION (VALUE-BASED)
# -------------------------

class PricingAnalysis(BaseModel):
    pricing_model: str
    cost_breakdown: Optional[str]
    value_for_money: Literal["excellent", "good", "average", "poor"]
    hidden_costs: Optional[List[str]]


# -------------------------
# REAL-WORLD USE CASE TESTING
# -------------------------

class UseCaseTest(BaseModel):
    scenario: str
    outcome: str
    effectiveness_rating: Optional[str]


class UseCaseSection(BaseModel):
    tests: List[UseCaseTest]


# -------------------------
# PROS & CONS (EVIDENCE-BASED, NOT GENERIC)
# -------------------------

class ProsCons(BaseModel):
    pros: List[str]
    cons: List[str]


# -------------------------
# COMPARISON SNAPSHOT (LIGHT LAYER)
# -------------------------

class ComparisonSnapshot(BaseModel):
    compared_to: List[str]
    key_differences: List[str]


# -------------------------
# INTEGRATIONS & ECOSYSTEM
# -------------------------

class Integration(BaseModel):
    name: str
    importance: Optional[str]
    notes: Optional[str]


class Ecosystem(BaseModel):
    integrations: List[Integration]
    api_available: Optional[bool]
    extensibility_notes: Optional[str]


# -------------------------
# LIMITATIONS (TRANSPARENCY CRITICAL IN 2026)
# -------------------------

class Limitations(BaseModel):
    known_issues: List[str]
    missing_features: Optional[List[str]]
    ideal_use_cases_only: Optional[List[str]]


# -------------------------
# ALTERNATIVES (SOFT COMPARISON LAYER)
# -------------------------

class Alternative(BaseModel):
    name: str
    why_consider: str


class AlternativesSection(BaseModel):
    alternatives: List[Alternative]


# -------------------------
# FINAL VERDICT ENGINE
# -------------------------

class Verdict(BaseModel):
    rating_score: Optional[float] = Field(ge=0, le=10)

    recommendation_type: Literal[
        "highly_recommended",
        "recommended",
        "conditional",
        "not_recommended"
    ]

    summary: str

    who_should_use: List[str]
    who_should_not_use: List[str]


# -------------------------
# TRUST & TRANSPARENCY
# -------------------------

class Transparency(BaseModel):
    testing_environment: Optional[str]
    data_sources: Optional[List[str]]
    affiliate_disclosure: Optional[bool] = True


# -------------------------
# CTA SYSTEM
# -------------------------

class CTASection(BaseModel):
    primary_cta: str
    secondary_cta: Optional[str] = None
    reassurance_text: Optional[str] = Field(
        default="Based on real-world usage and structured evaluation"
    )


# -------------------------
# FINAL IN-DEPTH REVIEW SCHEMA
# -------------------------

class InDepthReviewOutline(BaseModel):
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
        "Analytical", "Trustworthy", "Neutral",
        "Evaluative", "Professional", "Insightful"
    ]

    # Core structure
    hero: ReviewHero
    context: ReviewContext

    # Product breakdown
    overview: ProductOverview

    # Deep evaluation layers
    features: FeatureSection
    usability: UsabilityAnalysis
    performance: PerformanceMetrics

    # Value analysis
    pricing: PricingAnalysis

    # Real-world validation
    use_cases: UseCaseSection

    # Pros/cons (structured evidence)
    pros_cons: ProsCons

    # Ecosystem analysis
    ecosystem: Ecosystem

    # Limitations (critical trust builder)
    limitations: Limitations

    # Alternatives
    alternatives: AlternativesSection

    # Final decision system
    verdict: Verdict

    # Trust layer
    transparency: Transparency

    # CTA system
    cta: CTASection

    # Optimization Layer (2026 commercial review standard)
    conversion_goal: Literal[
        "purchase",
        "start_trial",
        "affiliate_click",
        "compare_products",
        "demo_request"
    ]

    decision_influence_goal: str = Field(
        default="Help user make confident purchase decision with minimal regret risk"
    )

    target_time_to_decision_seconds: Optional[int] = Field(
        default=300,
        description="Time for user to reach final decision"
    )

    target_word_count: int = Field(
        default=1600,
        ge=800,
        le=6000,
        description="In-depth reviews are long-form decision assets"
    )