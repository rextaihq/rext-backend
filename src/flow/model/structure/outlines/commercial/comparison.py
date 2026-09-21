"""Comparison outline schema — a NAME-KEYED, list-shaped comparison.

Every block here references a compared product by its NAME, never by its
position. That is the design rule of this file, and it is worth stating
because the schema used to do the opposite.

The previous shape was `products: ComparedProducts{product_a, product_b}` — a
fixed two-slot struct — while the feature matrix, pricing, use cases, verdict
and recommendations all pointed at products through the literal slot keys
`"product_a"` / `"product_b"`. Two defects followed from that, both of which
this schema exists to make impossible:

1. **Cardinality.** An approved brand promotion could not be added to a
   comparison whose two slots were already full, so the brand was pushed into
   the hero prose instead and never appeared in the comparison, the table, or
   the recommendation it was approved for.
2. **Silent misattribution.** Because identity was positional, ANY reordering
   of the slots re-pointed every sibling block at a different product without
   touching them: a row's `product_a_value` kept a competitor's pricing while
   `product_a` had become someone else, and a `winner_overall: "product_a"`
   silently became a verdict about a different company.

With names as the key, adding a product is an append, reordering is free, and a
reference either resolves to a real product or is visibly broken.
"""

from typing import List, Literal, Optional

from pydantic import BaseModel, Field

from src.flow.model.structure.outlines.product_names import PRODUCT_NAME_GUIDANCE

# Cardinality of the compared set AT OUTLINE-GENERATION time. Two is the
# minimum that is still a comparison; four is as many as a reader can hold in a
# table before it becomes a roundup (which is what best-tools is for).
#
# NOTE: this bound governs GENERATION only. After approval, `brand_slot` may
# prepend the approved brand to a full list, so a post-approval outline dict can
# legitimately carry MAX_COMPARED_PRODUCTS + 1 entries. That is deliberate:
# never evicting a real, user-approved competitor matters more than holding the
# ceiling, and approved outlines are plain dicts that are never re-validated
# through this model.
MIN_COMPARED_PRODUCTS = 2
MAX_COMPARED_PRODUCTS = 4

# -------------------------
# HERO / COMPARISON POSITIONING
# -------------------------


class ComparisonHero(BaseModel):
    headline: str = Field(
        description=(
            "Clear comparison intent naming the REAL products being compared "
            "(e.g. 'Ahrefs vs Semrush'). " + PRODUCT_NAME_GUIDANCE
        )
    )
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
    decision_stage: Optional[Literal["awareness", "consideration", "decision"]]
    urgency_level: Optional[Literal["low", "medium", "high"]]


# -------------------------
# PRODUCT PROFILE (THE ONLY PLACE A NAME IS DEFINED)
# -------------------------


class Product(BaseModel):
    name: str = Field(description=f"The product's real, specific name. {PRODUCT_NAME_GUIDANCE}")
    description: Optional[str]

    strengths: List[str]
    weaknesses: List[str]

    best_for: List[str]

    pricing_model: Optional[str]
    starting_price: Optional[str]

    link: Optional[str]


# -------------------------
# FEATURE COMPARISON MATRIX (CORE ENGINE)
# -------------------------


class FeatureComparisonRow(BaseModel):
    feature: str
    values: List[str] = Field(
        description=(
            "One value per product, in EXACTLY the same order and length as "
            "`products_compared`. Position i describes products_compared[i]. Use an empty "
            "string for a product the value is unknown for — never shorten the list, which "
            "would shift every later value onto the wrong product."
        )
    )


class FeatureComparisonMatrix(BaseModel):
    products_compared: List[str] = Field(
        description=(
            "The compared products' names, exactly as spelled in `products`, in table-column "
            f"order. {PRODUCT_NAME_GUIDANCE}"
        )
    )
    rows: List[FeatureComparisonRow]


# -------------------------
# USE CASE COMPARISON (MOST IMPORTANT IN 2026)
# -------------------------


class UseCaseComparison(BaseModel):
    use_case: str
    best_choice: str = Field(
        description=(
            "The NAME of the product that wins this use case, spelled exactly as in "
            "`products`, or the literal string 'tie'."
        )
    )
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
# HEAD-TO-HEAD SUMMARY / VERDICT (FAST DECISION LAYER)
# -------------------------


class HeadToHeadSummary(BaseModel):
    winner_overall: Optional[str] = Field(
        default=None,
        description=(
            "The NAME of the overall winner, spelled exactly as in `products`, or the literal "
            "string 'tie'. This is the article's verdict — it must name a product that is "
            "actually in the compared set."
        ),
    )

    best_for_beginners: str = Field(
        description="Name the winning product exactly as in `products`."
    )
    best_for_professionals: str = Field(
        description="Name the winning product exactly as in `products`."
    )
    best_budget_option: str = Field(
        description="Name the winning product exactly as in `products`."
    )
    best_feature_set: str = Field(description="Name the winning product exactly as in `products`.")
    best_support: str = Field(description="Name the winning product exactly as in `products`.")


# -------------------------
# PRICING COMPARISON
# -------------------------


class ProductPricing(BaseModel):
    product_name: str = Field(description="Exactly as spelled in `products`.")
    price: str = Field(description="That product's entry price or pricing summary.")


class PricingComparison(BaseModel):
    entries: List[ProductPricing] = Field(
        description="One entry per compared product, each keyed by the product's name."
    )
    value_analysis: str


# -------------------------
# PERFORMANCE / METRICS (IF APPLICABLE)
# -------------------------


class ProductMetricScore(BaseModel):
    product_name: str = Field(description="Exactly as spelled in `products`.")
    score: Optional[str]


class PerformanceMetrics(BaseModel):
    metric: str
    scores: List[ProductMetricScore] = Field(
        default_factory=list,
        description="One score per compared product, each keyed by the product's name.",
    )


# -------------------------
# MIGRATION INSIGHT (VERY IMPORTANT FOR 2026 SAAS SWITCHING)
# -------------------------


class MigrationInsight(BaseModel):
    from_product: str = Field(description="Exactly as spelled in `products`.")
    to_product: str = Field(description="Exactly as spelled in `products`.")
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
    recommended_product: str = Field(
        description=(
            "The NAME of the recommended product, spelled exactly as in `products`. Every "
            "recommendation must resolve to a product in the compared set."
        )
    )
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
# FAQ (COMPARISON-SPECIFIC QUESTIONS)
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
    reassurance_text: Optional[str] = Field(default="Unbiased comparison based on real-world usage")


# -------------------------
# FINAL COMPARISON OUTLINE SCHEMA
# -------------------------


class ComparisonOutline(BaseModel):
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
        "Analytical", "Comparative", "Neutral", "Decision-oriented", "Trustworthy", "Informative"
    ]

    # Core comparison flow
    hero: ComparisonHero
    comparison_context: ComparisonContext

    # The compared set — the single place a product NAME is defined. Every other
    # block below refers back to these names.
    products: List[Product] = Field(
        min_length=MIN_COMPARED_PRODUCTS,
        max_length=MAX_COMPARED_PRODUCTS,
        description=(
            f"The {MIN_COMPARED_PRODUCTS}-{MAX_COMPARED_PRODUCTS} products being compared, in "
            f"presentation order (the lead product first). {PRODUCT_NAME_GUIDANCE}"
        ),
    )

    # Core decision engine
    feature_matrix: FeatureComparisonMatrix

    # Use-case intelligence
    use_cases: UseCaseSection

    # Decision system
    decision_framework: DecisionFramework

    # Fast decision summary layer / verdict
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

    # FAQ layer (AEO / PAA coverage for high-intent comparison queries)
    faqs: FAQSection

    # CTA system
    cta: CTASection

    # Optimization Layer (2026 commercial decision standard)
    conversion_goal: Literal[
        "choose_product", "start_trial", "switch_product", "book_demo", "affiliate_click"
    ]

    decision_time_target_seconds: Optional[int] = Field(
        default=150, description="Ideal time for user to reach decision"
    )

    target_word_count: int = Field(
        default=2000,
        ge=1500,
        le=3000,
        description="Comparison pages are structured decision engines",
    )
