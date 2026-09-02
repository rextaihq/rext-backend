# from typing import List, Optional
# from pydantic import Field
# from src.flow.model.structure.outlines.base import BaseOutline, Section


# class BestToolsOutline(BaseOutline):
#     """Outline for content listing the 'best' tools or products in a category."""
#     category_name: str = Field(description="The category of tools (e.g., 'CRM Software').")
#     total_tools_to_list: int = Field(description="Number of tools to focus on.")
#     ranking_criteria: List[str] = Field(description="How the tools were selected and ranked.")
#     top_pick_declaration: Optional[bool] = Field(default=True, description="Whether to highlight a 'best overall' tool.")

from typing import List, Literal, Optional

from pydantic import BaseModel, Field

# -------------------------
# HERO / TOOL CATEGORY POSITIONING
# -------------------------


class BestToolsHero(BaseModel):
    headline: str = Field(description="Clear intent-driven title (e.g., 'Best AI Writing Tools')")
    subheadline: str = Field(description="Explains selection criteria and audience")

    primary_cta: str = Field(default="Explore Tools")
    secondary_cta: Optional[str] = Field(default="Compare All")


# -------------------------
# SELECTION METHODOLOGY (CRITICAL FOR TRUST IN 2026)
# -------------------------


class SelectionCriteria(BaseModel):
    criteria: List[str] = Field(
        description="How tools were selected (performance, usability, pricing, etc.)"
    )
    evaluation_method: Optional[str]
    update_frequency: Optional[str]


# -------------------------
# TOOL PROFILE (CORE ENTITY)
# -------------------------


class Tool(BaseModel):
    name: str
    description: str

    key_features: List[str]
    pros: List[str]
    cons: List[str]

    pricing_model: Optional[str]
    starting_price: Optional[str]

    best_for: List[str]

    rating_score: Optional[float] = Field(ge=0, le=10, description="Editorial or AI-based scoring")

    link: Optional[str]


# -------------------------
# RANKING SYSTEM (NOT JUST LIST ORDER)
# -------------------------


class RankedTool(BaseModel):
    rank: int
    tool: Tool
    ranking_reason: str


class ToolRanking(BaseModel):
    category: str
    ranked_tools: List[RankedTool]


# -------------------------
# USE CASE MATCHING (VERY IMPORTANT IN 2026)
# -------------------------


class UseCaseMatch(BaseModel):
    use_case: str
    best_tool: str
    reason: str


class UseCaseSection(BaseModel):
    matches: List[UseCaseMatch]


# -------------------------
# FEATURE COMPARISON MATRIX
# -------------------------


class ComparisonRow(BaseModel):
    feature: str
    tool_values: List[str]


class ComparisonMatrix(BaseModel):
    tools_compared: List[str]
    rows: List[ComparisonRow]


# -------------------------
# CATEGORY BREAKDOWN (SEGMENTATION)
# -------------------------


class ToolCategory(BaseModel):
    name: str
    description: str
    tools: List[str]


class CategorySection(BaseModel):
    categories: List[ToolCategory]


# -------------------------
# PRICING INSIGHTS (DECISION DRIVER)
# -------------------------


class PricingInsight(BaseModel):
    tool_name: str
    pricing_summary: str
    value_assessment: str


# -------------------------
# DECISION GUIDE (CHOICE ASSISTANCE)
# -------------------------


class DecisionGuide(BaseModel):
    best_for_beginners: str
    best_for_professionals: str
    best_budget_option: str
    best_premium_option: str
    best_overall: str


# -------------------------
# SOCIAL PROOF (TRUST SIGNALS)
# -------------------------


class SocialProof(BaseModel):
    user_reviews_summary: List[str]
    adoption_metrics: Optional[List[str]] = Field(default_factory=list)
    industry_mentions: Optional[List[str]] = Field(default_factory=list)


# -------------------------
# TOOL UPDATE INTELLIGENCE
# -------------------------


class UpdateInfo(BaseModel):
    last_updated: str
    frequency_of_updates: Optional[str]
    ai_review_enabled: bool = True


# -------------------------
# FAQ (BEST-TOOLS-SPECIFIC QUESTIONS)
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
    reassurance_text: Optional[str] = Field(default="No bias rankings. Based on real use cases.")


# -------------------------
# FINAL BEST TOOLS SCHEMA
# -------------------------


class BestToolsOutline(BaseModel):
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
        "Analytical", "Comparative", "Informative", "Trustworthy", "Neutral", "Decision-oriented"
    ]

    # Core structure
    hero: BestToolsHero
    selection_criteria: SelectionCriteria

    # Ranking system (core logic)
    rankings: List[ToolRanking]

    # Tool categories
    categories: CategorySection

    # Use-case mapping
    use_cases: UseCaseSection

    # Feature-level comparison
    comparison_matrix: Optional[ComparisonMatrix]

    # Pricing insights
    pricing_insights: List[PricingInsight]

    # Decision support layer
    decision_guide: DecisionGuide

    # Trust layer
    social_proof: SocialProof

    # Maintenance layer (very important in fast-moving SaaS/tools ecosystem)
    update_info: UpdateInfo

    # FAQ layer (AEO / PAA coverage for high-intent tool-selection queries)
    faqs: FAQSection

    # CTA system
    cta: CTASection

    # Optimization Layer (2026 commercial intent standard)
    conversion_goal: Literal[
        "tool_signup", "affiliate_click", "comparison_engagement", "trial_start", "demo_request"
    ]

    decision_speed_goal_seconds: Optional[int] = Field(
        default=120, description="Time to help user pick a tool"
    )

    target_word_count: int = Field(
        default=1200, ge=600, le=4000, description="Best tools pages are structured decision hubs"
    )
