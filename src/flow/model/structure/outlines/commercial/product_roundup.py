# from typing import List, Optional
# from pydantic import Field
# from src.flow.model.structure.outlines.base import BaseOutline, Section


# class ProductRoundupOutline(BaseOutline):
#     """Outline for content summarizing several products or services."""
#     category_name: str = Field(description="The general category for the roundup.")
#     total_products: int = Field(description="Number of products included.")
#     roundup_theme: Optional[str] = Field(description="E.g., 'Budget-friendly', 'For Beginners'.")
#     best_value_pick: Optional[str] = Field(description="The best value product in the list.")
#     premium_pick: Optional[str] = Field(description="The premium/expensive option in the list.")

from typing import List, Optional, Literal
from pydantic import BaseModel, Field


# -------------------------
# HERO / CATEGORY POSITIONING
# -------------------------

class RoundupHero(BaseModel):
    headline: str = Field(description="e.g., 'Best CRM Tools in 2026'")
    subheadline: str = Field(description="Explains selection scope and audience")

    primary_cta: str = Field(default="Compare Top Picks")
    secondary_cta: Optional[str] = Field(default="Explore All Tools")


# -------------------------
# SELECTION METHODOLOGY (TRUST FOUNDATION)
# -------------------------

class SelectionMethodology(BaseModel):
    criteria: List[str]
    testing_process: Optional[str]
    update_frequency: Optional[str]
    editorial_policy: Optional[str]


# -------------------------
# PRODUCT ENTITY (CORE ITEM)
# -------------------------

class ProductItem(BaseModel):
    name: str
    description: str

    key_features: List[str]
    pros: List[str]
    cons: List[str]

    pricing_model: Optional[str]
    starting_price: Optional[str]

    best_for: List[str]

    rating_score: Optional[float] = Field(ge=0, le=10)

    affiliate_link: Optional[str]


# -------------------------
# RANKED PRODUCT ENTRY
# -------------------------

class RankedProduct(BaseModel):
    rank: int
    product: ProductItem
    reason_for_rank: str


# -------------------------
# BEST PICKS (STRUCTURED GROUPING)
# -------------------------

class BestPickGroup(BaseModel):
    group_name: str  # e.g., "Best Overall", "Best Budget"
    description: str
    products: List[RankedProduct]


class BestPickSection(BaseModel):
    groups: List[BestPickGroup]


# -------------------------
# USE CASE MATCHING (CRITICAL IN 2026)
# -------------------------

class UseCaseMatch(BaseModel):
    use_case: str
    recommended_product: str
    reasoning: str


class UseCaseSection(BaseModel):
    matches: List[UseCaseMatch]


# -------------------------
# FEATURE COMPARISON MATRIX (DECISION LAYER)
# -------------------------

class ComparisonRow(BaseModel):
    feature: str
    values: List[str]


class ComparisonMatrix(BaseModel):
    products: List[str]
    rows: List[ComparisonRow]


# -------------------------
# PRICING ANALYSIS
# -------------------------

class PricingAnalysis(BaseModel):
    product_name: str
    price_range: str
    value_assessment: Literal["excellent", "good", "average", "poor"]


# -------------------------
# DECISION GUIDE (FAST PICK SYSTEM)
# -------------------------

class DecisionGuide(BaseModel):
    best_overall: str
    best_budget: str
    best_premium: str
    best_for_beginners: str
    best_for_advanced_users: str


# -------------------------
# ALTERNATIVES (OPTIONAL EXPANSION LAYER)
# -------------------------

class Alternative(BaseModel):
    name: str
    reason_to_consider: str


class AlternativesSection(BaseModel):
    alternatives: List[Alternative]


# -------------------------
# SOCIAL PROOF (TRUST SIGNALS)
# -------------------------

class SocialProof(BaseModel):
    user_reviews_summary: List[str]
    expert_opinions: Optional[List[str]] = Field(default_factory=list)
    adoption_metrics: Optional[List[str]] = Field(default_factory=list)


# -------------------------
# FAQ (ROUNDUP-SPECIFIC QUESTIONS)
# -------------------------

class FAQItem(BaseModel):
    question: str
    answer: str


class FAQSection(BaseModel):
    faqs: List[FAQItem]


# -------------------------
# CTA SYSTEM
# -------------------------

class CTASection(BaseModel):
    primary_cta: str
    secondary_cta: Optional[str] = None
    reassurance_text: Optional[str] = Field(
        default="Hand-picked based on real-world usage and testing"
    )


# -------------------------
# FINAL PRODUCT ROUNDUP SCHEMA
# -------------------------

class ProductRoundupOutline(BaseModel):
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
        "Comparative", "Analytical", "Editorial",
        "Trustworthy", "Neutral", "Decision-oriented"
    ]

    # Core structure
    hero: RoundupHero
    methodology: SelectionMethodology

    # Main roundup structure (core ranking engine)
    best_picks: BestPickSection

    # Use-case matching
    use_cases: UseCaseSection

    # Decision support layer
    decision_guide: DecisionGuide

    # Comparison system
    comparison_matrix: Optional[ComparisonMatrix]

    # Pricing intelligence
    pricing: List[PricingAnalysis]

    # Expansion layer
    alternatives: Optional[AlternativesSection]

    # Trust layer
    social_proof: SocialProof

    # FAQ layer (AEO / PAA coverage for high-intent roundup queries)
    faqs: FAQSection

    # CTA system
    cta: CTASection

    # Optimization Layer (2026 commercial intent standard)
    conversion_goal: Literal[
        "affiliate_click",
        "product_signup",
        "trial_start",
        "purchase",
        "comparison_engagement"
    ]

    decision_speed_goal_seconds: Optional[int] = Field(
        default=180,
        description="Time to help user pick a product"
    )

    target_word_count: int = Field(
        default=1400,
        ge=700,
        le=5000,
        description="Roundups are structured decision pages"
    )