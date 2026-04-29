# from typing import List, Optional
# from pydantic import Field
# from src.flow.model.structure.outlines.base import BaseOutline, Section


# class ComparisonSection(Section):
#     """Specifically for comparing items."""
#     comparison_criteria: List[str] = Field(description="Aspects being compared (e.g., 'Pricing', 'Performance').")


# class ComparisonOutline(BaseOutline):
#     """Outline for content comparing two or more products or services."""
#     compared_entities: List[str] = Field(description="The items being compared.")
#     winner_declaration: Optional[bool] = Field(default=False, description="Whether to declare a winner.")
#     comparison_table_included: bool = Field(default=True, description="Whether a comparison table is required.")
#     sections: List[ComparisonSection] = Field(description="Detailed comparison sections.")

from typing import List, Optional, Literal
from pydantic import BaseModel, Field


# -------------------------
# HERO / COMPARISON POSITIONING
# -------------------------

class ComparisonHero(BaseModel):
    headline: str = Field(description="Clear comparison intent (e.g., 'Tool A vs Tool B')")
    subheadline: str = Field(description="Explains who this comparison is for and decision context")

    primary_cta: str = Field(default="Start Free Trial")
    secondary_cta: Optional[str] = Field(default="See Full Comparison")


# -------------------------
# COMPARISON CONTEXT (CRITICAL IN 2026)
# -------------------------

class ComparisonContext(BaseModel):
    comparison_reason: List[str] = Field(
        description="Why users compare these products (price, features, complexity, etc.)"
    )
    decision_stage: Optional[Literal[
        "awareness",
        "consideration",
        "decision"
    ]]
    urgency_level: Optional[Literal["low", "medium", "high"]]


# -------------------------
# PRODUCT PROFILE (BOTH SIDES)
# -------------------------

class Product(BaseModel):
    name: str
    description: Optional[str]

    strengths: List[str]
    weaknesses: List[str]

    best_for: List[str]

    pricing_model: Optional[str]
    starting_price: Optional[str]

    link: Optional[str]


class ComparedProducts(BaseModel):
    product_a: Product
    product_b: Product


# -------------------------
# FEATURE COMPARISON MATRIX (CORE ENGINE)
# -------------------------

class FeatureComparisonRow(BaseModel):
    feature: str
    product_a_value: str
    product_b_value: str


class FeatureComparisonMatrix(BaseModel):
    rows: List[FeatureComparisonRow]


# -------------------------
# USE CASE COMPARISON (MOST IMPORTANT IN 2026)
# -------------------------

class UseCaseComparison(BaseModel):
    use_case: str
    best_choice: Literal["product_a", "product_b", "tie"]
    reasoning: str


class UseCaseSection(BaseModel):
    comparisons: List[UseCaseComparison]


# -------------------------
# DECISION FACTORS (WEIGHTED EVALUATION SYSTEM)
# -------------------------

class DecisionFactor(BaseModel):
    factor: str
    importance: Literal["low", "medium", "high"]
    explanation: Optional[str]


class DecisionFramework(BaseModel):
    factors: List[DecisionFactor]


# -------------------------
# HEAD-TO-HEAD SUMMARY (FAST DECISION LAYER)
# -------------------------

class HeadToHeadSummary(BaseModel):
    winner_overall: Optional[Literal["product_a", "product_b", "tie"]]

    best_for_beginners: str
    best_for_professionals: str
    best_budget_option: str
    best_feature_set: str
    best_support: str


# -------------------------
# PRICING COMPARISON
# -------------------------

class PricingComparison(BaseModel):
    product_a_price: str
    product_b_price: str
    value_analysis: str


# -------------------------
# PERFORMANCE / METRICS (IF APPLICABLE)
# -------------------------

class PerformanceMetrics(BaseModel):
    metric: str
    product_a_score: Optional[str]
    product_b_score: Optional[str]


# -------------------------
# MIGRATION INSIGHT (VERY IMPORTANT FOR 2026 SAAS SWITCHING)
# -------------------------

class MigrationInsight(BaseModel):
    from_product: str
    to_product: str
    ease_of_switch: str
    steps_summary: List[str]


# -------------------------
# SOCIAL PROOF (DECISION VALIDATION)
# -------------------------

class SocialProof(BaseModel):
    user_reviews_summary: List[str]
    expert_opinions: Optional[List[str]] = Field(default_factory=list)
    case_studies: Optional[List[str]] = Field(default_factory=list)


# -------------------------
# RECOMMENDATION ENGINE
# -------------------------

class Recommendation(BaseModel):
    scenario: str
    recommended_product: Literal["product_a", "product_b"]
    justification: str


class RecommendationEngine(BaseModel):
    recommendations: List[Recommendation]


# -------------------------
# BIAS TRANSPARENCY (2026 TRUST REQUIREMENT)
# -------------------------

class Transparency(BaseModel):
    data_sources: Optional[List[str]]
    editorial_policy: Optional[str]
    affiliate_disclosure: Optional[bool] = True


# -------------------------
# CTA SYSTEM
# -------------------------

class CTASection(BaseModel):
    primary_cta: str
    secondary_cta: Optional[str] = None
    reassurance_text: Optional[str] = Field(
        default="Unbiased comparison based on real-world usage"
    )


# -------------------------
# FINAL COMPARISON OUTLINE SCHEMA
# -------------------------

class ComparisonOutline(BaseModel):
    # Core metadata
    title: str
    slug_suggestion: str = Field(pattern=r"^[a-z0-9-]+$")
    focus_keyphrase: str

    target_audience: List[str]
    tone: Literal[
        "Analytical", "Comparative", "Neutral",
        "Decision-oriented", "Trustworthy", "Informative"
    ]

    # Core comparison flow
    hero: ComparisonHero
    comparison_context: ComparisonContext

    # Product side-by-side
    products: ComparedProducts

    # Core decision engine
    feature_matrix: FeatureComparisonMatrix

    # Use-case intelligence
    use_cases: UseCaseSection

    # Decision system
    decision_framework: DecisionFramework

    # Fast decision summary layer
    head_to_head: HeadToHeadSummary

    # Pricing intelligence
    pricing: PricingComparison

    # Performance metrics (optional but powerful)
    performance: Optional[PerformanceMetrics]

    # Migration guidance (critical for SaaS switching)
    migration: Optional[MigrationInsight]

    # Trust layer
    social_proof: SocialProof
    transparency: Transparency

    # Recommendation engine
    recommendations: RecommendationEngine

    # CTA system
    cta: CTASection

    # Optimization Layer (2026 commercial decision standard)
    conversion_goal: Literal[
        "choose_product",
        "start_trial",
        "switch_product",
        "book_demo",
        "affiliate_click"
    ]

    decision_time_target_seconds: Optional[int] = Field(
        default=150,
        description="Ideal time for user to reach decision"
    )

    target_word_count: int = Field(
        default=1400,
        ge=700,
        le=4500,
        description="Comparison pages are structured decision engines"
    )