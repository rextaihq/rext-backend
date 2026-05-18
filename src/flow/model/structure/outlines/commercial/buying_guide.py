# from typing import List, Optional
# from pydantic import Field
# from src.flow.model.structure.outlines.base import BaseOutline, Section


# class BuyingGuideOutline(BaseOutline):
#     """Outline for content helping users make a purchasing decision."""
#     product_category: str = Field(description="The category being bought (e.g., 'Laptops').")
#     key_features_to_consider: List[str] = Field(description="Important features buyers should look for.")
#     budget_tiers: Optional[List[str]] = Field(description="Summary of pricing or budget levels.")
#     common_mistakes_to_avoid: Optional[List[str]] = Field(description="Pitfalls buyers make.")

from typing import List, Optional, Literal
from pydantic import BaseModel, Field


# -------------------------
# HERO / PURCHASE INTENT ALIGNMENT
# -------------------------

class BuyingGuideHero(BaseModel):
    headline: str = Field(description="Clear purchase intent headline (e.g., 'How to choose the best CRM')")
    subheadline: str = Field(description="Explains who this guide is for and what it helps decide")

    primary_cta: str = Field(default="Compare Options")
    secondary_cta: Optional[str] = Field(default="See Recommendations")


# -------------------------
# BUYER INTENT ANALYSIS (CRITICAL IN 2026)
# -------------------------

class BuyerIntent(BaseModel):
    user_goals: List[str]
    pain_points: List[str]
    urgency_level: Optional[Literal["low", "medium", "high"]]
    decision_stage: Optional[Literal[
        "researching",
        "comparing",
        "ready_to_buy"
    ]]


# -------------------------
# REQUIREMENT FRAMEWORK (CORE OF MODERN BUYING GUIDES)
# -------------------------

class Requirement(BaseModel):
    name: str
    importance: Literal["low", "medium", "high"]
    explanation: str


class RequirementFramework(BaseModel):
    requirements: List[Requirement]


# -------------------------
# BUYER SEGMENTS (2026 PERSONALIZATION STANDARD)
# -------------------------

class BuyerSegment(BaseModel):
    segment_name: str
    description: str
    needs: List[str]
    recommended_type: Optional[str]


class BuyerSegments(BaseModel):
    segments: List[BuyerSegment]


# -------------------------
# PRODUCT CATEGORY OPTIONS
# -------------------------

class ProductOption(BaseModel):
    name: str
    description: str
    pros: List[str]
    cons: List[str]
    best_for: List[str]


class ProductOptions(BaseModel):
    options: List[ProductOption]


# -------------------------
# COMPARISON MATRIX (DECISION ENGINE CORE)
# -------------------------

class ComparisonRow(BaseModel):
    criterion: str
    options_values: List[str]


class ComparisonMatrix(BaseModel):
    options: List[str]
    rows: List[ComparisonRow]


# -------------------------
# DECISION WEIGHTING SYSTEM (VERY IMPORTANT IN 2026)
# -------------------------

class DecisionFactor(BaseModel):
    factor: str
    weight: Literal["low", "medium", "high"]
    explanation: Optional[str]


class DecisionFramework(BaseModel):
    factors: List[DecisionFactor]


# -------------------------
# USE CASE MATCHING
# -------------------------

class UseCaseMatch(BaseModel):
    use_case: str
    best_option: str
    reason: str


class UseCaseSection(BaseModel):
    matches: List[UseCaseMatch]


# -------------------------
# COMMON MISTAKES (HIGH IMPACT SECTION)
# -------------------------

class Mistake(BaseModel):
    mistake: str
    consequence: str
    how_to_avoid: str


class MistakesSection(BaseModel):
    mistakes: List[Mistake]


# -------------------------
# PRICING ALIGNMENT
# -------------------------

class PricingInsight(BaseModel):
    option_name: str
    price_range: str
    value_assessment: str


class PricingSection(BaseModel):
    insights: List[PricingInsight]


# -------------------------
# FINAL RECOMMENDATION ENGINE
# -------------------------

class Recommendation(BaseModel):
    scenario: str
    recommended_option: str
    justification: str


class RecommendationEngine(BaseModel):
    recommendations: List[Recommendation]


# -------------------------
# TRUST + SOCIAL PROOF
# -------------------------

class SocialProof(BaseModel):
    expert_opinions: Optional[List[str]] = Field(default_factory=list)
    user_reviews_summary: Optional[List[str]] = Field(default_factory=list)
    adoption_metrics: Optional[List[str]] = Field(default_factory=list)


# -------------------------
# CTA SYSTEM
# -------------------------

class CTASection(BaseModel):
    primary_cta: str
    secondary_cta: Optional[str] = None
    reassurance_text: Optional[str] = Field(
        default="Unbiased recommendations based on real use cases"
    )


# -------------------------
# FINAL BUYING GUIDE SCHEMA
# -------------------------

class BuyingGuideOutline(BaseModel):
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
        "Analytical", "Educational", "Decision-oriented",
        "Trustworthy", "Neutral", "Guided", "Professional"
    ]

    # Core decision flow
    hero: BuyingGuideHero

    # Buyer intelligence layer
    buyer_intent: BuyerIntent

    # Requirement system (core of modern buying guides)
    requirement_framework: RequirementFramework

    # Buyer segmentation
    buyer_segments: BuyerSegments

    # Available options
    product_options: ProductOptions

    # Comparison engine
    comparison_matrix: Optional[ComparisonMatrix]

    # Decision weighting system
    decision_framework: DecisionFramework

    # Use-case mapping
    use_cases: UseCaseSection

    # Pricing intelligence
    pricing: PricingSection

    # Mistake prevention (conversion booster)
    mistakes: MistakesSection

    # Final recommendation engine
    recommendations: RecommendationEngine

    # Trust layer
    social_proof: SocialProof

    # CTA system
    cta: CTASection

    # Optimization Layer (2026 commercial intent standard)
    conversion_goal: Literal[
        "purchase",
        "start_trial",
        "request_demo",
        "compare_products",
        "affiliate_click"
    ]

    decision_confidence_goal: str = Field(
        default="Help user make confident, low-regret purchase decision"
    )

    target_time_to_decision_seconds: Optional[int] = Field(
        default=240,
        description="Ideal time to reach final product decision"
    )

    target_word_count: int = Field(
        default=1500,
        ge=700,
        le=5000,
        description="Buying guides are deep decision frameworks"
    )