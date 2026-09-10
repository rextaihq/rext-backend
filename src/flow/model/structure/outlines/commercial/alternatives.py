# from typing import List, Optional
# from pydantic import Field
# from src.flow.model.structure.outlines.base import BaseOutline, Section


# class AlternativesOutline(BaseOutline):
#     """Outline for content suggesting alternatives to a specific entity."""
#     primary_entity: str = Field(description="The primary entity (e.g., 'Mailchimp').")
#     reasons_for_alternatives: List[str] = Field(description="Why someone would look for alternatives.")
#     total_alternatives_to_list: int = Field(description="Total number of alternatives to cover.")
#     best_overall_alternative: Optional[str] = Field(description="The top recommended alternative.")


from typing import List, Literal, Optional

from pydantic import BaseModel, Field

# -------------------------
# HERO / POSITIONING
# -------------------------


class AlternativesHero(BaseModel):
    headline: str = Field(description="Clear comparison intent (e.g., 'Best alternatives to X')")
    subheadline: str = Field(description="Explains who should switch and why")

    primary_cta: str = Field(default="Try Our Product")
    secondary_cta: Optional[str] = Field(
        default="Compare Features", description="Comparison-focused navigation CTA"
    )


# -------------------------
# WHY USERS SEARCH ALTERNATIVES (INTENT MODEL)
# -------------------------


class SearchIntent(BaseModel):
    reasons: List[str] = Field(
        description="Why users look for alternatives (price, missing features, complexity, etc.)"
    )
    switching_triggers: Optional[List[str]] = Field(default_factory=list)


# -------------------------
# COMPETITOR PROFILE
# -------------------------


class Competitor(BaseModel):
    name: str
    description: Optional[str]

    strengths: List[str]
    weaknesses: List[str]

    pricing_model: Optional[str]
    target_users: Optional[List[str]]

    link: Optional[str]


# -------------------------
# COMPARISON MATRIX (CORE DECISION TOOL)
# -------------------------


class ComparisonRow(BaseModel):
    feature: str
    ours: str
    competitor: str


class ComparisonMatrix(BaseModel):
    competitor_name: str
    rows: List[ComparisonRow]


# -------------------------
# FEATURE DIFFERENTIATION
# -------------------------


class Differentiation(BaseModel):
    unique_advantages: List[str]
    key_differences: List[str]
    positioning_statement: str


# -------------------------
# USE CASE MATCHING (IMPORTANT FOR 2026 BUYING BEHAVIOR)
# -------------------------


class UseCaseMatch(BaseModel):
    use_case: str
    best_option: str
    reason: str


class UseCaseSection(BaseModel):
    matches: List[UseCaseMatch]


# -------------------------
# MIGRATION / SWITCHING GUIDE
# -------------------------


class MigrationStep(BaseModel):
    step: str
    description: str


class MigrationGuide(BaseModel):
    from_competitor: str
    steps: List[MigrationStep]
    estimated_time: Optional[str]


# -------------------------
# PRICING COMPARISON
# -------------------------


class PricingComparison(BaseModel):
    competitor_name: str
    pricing_summary: str
    value_assessment: str


# -------------------------
# SOCIAL PROOF (DECISION VALIDATION)
# -------------------------


class SocialProof(BaseModel):
    testimonials: List[str]
    case_studies: Optional[List[str]] = Field(default_factory=list)
    switching_success_stories: Optional[List[str]] = Field(default_factory=list)


# -------------------------
# DECISION GUIDANCE ENGINE
# -------------------------


class DecisionGuide(BaseModel):
    who_should_choose_us: List[str]
    who_should_choose_competitor: Optional[List[str]] = Field(default_factory=list)
    best_fit_scenarios: List[str]


# -------------------------
# ALTERNATIVES LIST
# -------------------------


class AlternativesList(BaseModel):
    competitors: List[Competitor]


# -------------------------
# FAQ (ALTERNATIVES-SPECIFIC QUESTIONS)
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
        default="No lock-in. Easy migration available.", description="Reduces switching hesitation"
    )


# -------------------------
# FINAL ALTERNATIVES PAGE SCHEMA
# -------------------------


class AlternativesOutline(BaseModel):
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
        "Comparative", "Analytical", "Trustworthy", "Clear", "Neutral", "Decision-oriented"
    ]

    # Core intent layer
    search_intent: SearchIntent

    # Page structure (decision flow)
    hero: AlternativesHero
    alternatives_list: AlternativesList

    # Comparison system (core of page)
    comparison_matrices: List[ComparisonMatrix]

    # Differentiation
    differentiation: Differentiation

    # Use-case alignment
    use_cases: UseCaseSection

    # Decision guidance
    decision_guide: DecisionGuide

    # Migration support (very important in 2026 SaaS switching behavior)
    migration: Optional[MigrationGuide]

    # Pricing comparison
    pricing_comparisons: Optional[List[PricingComparison]]

    # Trust layer
    social_proof: SocialProof

    # FAQ layer (AEO / PAA coverage for switching-intent queries)
    faqs: FAQSection

    # CTA system
    cta: CTASection

    # Optimization Layer (2026 commercial intent standard)
    conversion_goal: Literal[
        "switch_product", "start_trial", "book_demo", "compare_features", "sign_up"
    ]

    decision_confidence_goal: Optional[str] = Field(
        default="Increase user confidence in choosing correct tool",
        description="Core psychological goal of page",
    )

    target_time_to_decision_seconds: Optional[int] = Field(
        default=180, description="Time for user to make informed choice"
    )

    target_word_count: int = Field(
        default=1200,
        ge=600,
        le=4000,
        description="Alternatives pages are medium-depth decision pages",
    )
