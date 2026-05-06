# from typing import List, Optional
# from pydantic import Field
# from src.flow.model.structure.outlines.base import BaseOutline, Section


# class ProsConsSection(Section):
#     """Specifically for pros and cons lists."""
#     pros: List[str] = Field(description="List of positive aspects.")
#     cons: List[str] = Field(description="List of negative aspects.")


# class ProsConsOutline(BaseOutline):
#     """Outline for content highlighting the pros and cons of an entity."""
#     entity_name: str = Field(description="The subject being discussed.")
#     overall_sentiment: Optional[str] = Field(description="Is it generally positive or negative?")
#     final_recommendation: Optional[str] = Field(description="Who this is best suited for.")
#     sections: List[ProsConsSection] = Field(description="Detailed pros and cons sections.")


from typing import List, Optional, Literal
from pydantic import BaseModel, Field


# -------------------------
# HERO / DECISION POSITIONING
# -------------------------

class ProsConsHero(BaseModel):
    product_name: str
    headline: str = Field(description="e.g., 'Is X worth it? Pros & Cons explained'")
    subheadline: str = Field(description="Clear decision framing for users")

    primary_cta: str = Field(default="Try Product")
    secondary_cta: Optional[str] = Field(default="Compare Alternatives")


# -------------------------
# CONTEXT (WHY USERS CARE)
# -------------------------

class DecisionContext(BaseModel):
    user_intent: List[str]
    decision_stage: Optional[Literal[
        "researching",
        "comparing",
        "final_decision"
    ]]
    urgency_level: Optional[Literal["low", "medium", "high"]]


# -------------------------
# PROS (STRUCTURED VALUE SIGNALS)
# -------------------------

class ProItem(BaseModel):
    point: str
    impact_level: Literal["low", "medium", "high"]
    explanation: Optional[str]
    real_world_example: Optional[str]


class ProsSection(BaseModel):
    pros: List[ProItem]


# -------------------------
# CONS (STRUCTURED LIMITATIONS)
# -------------------------

class ConItem(BaseModel):
    point: str
    severity: Literal["low", "medium", "high"]
    impact: str = Field(description="What problem this causes in real usage")
    workaround: Optional[str]


class ConsSection(BaseModel):
    cons: List[ConItem]


# -------------------------
# TRADE-OFF ANALYSIS (IMPORTANT 2026 UPGRADE)
# -------------------------

class TradeOff(BaseModel):
    dimension: str
    advantage: str
    disadvantage: str


class TradeOffSection(BaseModel):
    tradeoffs: List[TradeOff]


# -------------------------
# USE CASE FIT (CRITICAL FOR DECISION MAKING)
# -------------------------

class UseCaseFit(BaseModel):
    scenario: str
    fit_level: Literal["excellent", "good", "poor"]
    reason: str


class UseCaseSection(BaseModel):
    fits: List[UseCaseFit]


# -------------------------
# FEATURE-IMPACT MAPPING (DEEPER THAN PRO/CON LISTS)
# -------------------------

class FeatureImpact(BaseModel):
    feature: str
    benefit: Optional[str]
    drawback: Optional[str]
    importance: Literal["low", "medium", "high"]


class FeatureImpactSection(BaseModel):
    features: List[FeatureImpact]


# -------------------------
# DECISION SUMMARY (FAST SCANNING LAYER)
# -------------------------

class DecisionSummary(BaseModel):
    overall_assessment: Literal[
        "highly_recommended",
        "recommended",
        "conditional",
        "not_recommended"
    ]

    who_should_use: List[str]
    who_should_avoid: List[str]


# -------------------------
# COMPARATIVE CONTEXT (LIGHTWEIGHT BENCHMARKING)
# -------------------------

class ComparisonContext(BaseModel):
    compared_to: List[str]
    key_difference_summary: List[str]


# -------------------------
# RISK ANALYSIS (NEW IN MODERN DECISION SYSTEMS)
# -------------------------

class RiskItem(BaseModel):
    risk: str
    likelihood: Literal["low", "medium", "high"]
    mitigation: Optional[str]


class RiskAnalysis(BaseModel):
    risks: List[RiskItem]


# -------------------------
# VALUE ASSESSMENT
# -------------------------

class ValueAssessment(BaseModel):
    cost_value_ratio: Literal["excellent", "good", "average", "poor"]
    justification: str


# -------------------------
# SOCIAL VALIDATION
# -------------------------

class SocialProof(BaseModel):
    user_feedback_summary: List[str]
    expert_opinions: Optional[List[str]] = Field(default_factory=list)
    adoption_signals: Optional[List[str]] = Field(default_factory=list)


# -------------------------
# CTA SYSTEM
# -------------------------

class CTASection(BaseModel):
    primary_cta: str
    secondary_cta: Optional[str] = None
    reassurance_text: Optional[str] = Field(
        default="Balanced analysis based on real-world usage patterns"
    )


# -------------------------
# FINAL PROS & CONS SCHEMA
# -------------------------

class ProsConsOutline(BaseModel):
    # Core metadata
    title: str
    slug_suggestion: str = Field(pattern=r"^[a-z0-9-]+$")
    focus_keyphrase: str

    target_audience: List[str]
    tone: Literal[
        "Balanced", "Analytical", "Neutral",
        "Trustworthy", "Decision-oriented", "Evaluative"
    ]

    # Core decision structure
    hero: ProsConsHero
    context: DecisionContext

    # Core evaluation layers
    pros: ProsSection
    cons: ConsSection

    # Advanced decision layers (2026 upgrade)
    tradeoffs: TradeOffSection
    feature_impact: FeatureImpactSection

    # Use-case validation
    use_cases: UseCaseSection

    # Risk layer (modern addition)
    risk_analysis: RiskAnalysis

    # Value judgment
    value_assessment: ValueAssessment

    # Lightweight comparison context
    comparison_context: ComparisonContext

    # Final decision logic
    decision_summary: DecisionSummary

    # Trust layer
    social_proof: SocialProof

    # CTA system
    cta: CTASection

    # Optimization Layer (2026 commercial intent standard)
    conversion_goal: Literal[
        "purchase",
        "start_trial",
        "affiliate_click",
        "compare_products",
        "demo_request"
    ]

    decision_clarity_goal: str = Field(
        default="Help user make confident yes/no decision with full trade-off awareness"
    )

    target_time_to_decision_seconds: Optional[int] = Field(
        default=120,
        description="Time for user to reach decision clarity"
    )

    target_word_count: int = Field(
        default=1000,
        ge=500,
        le=3500,
        description="Pros & cons pages are fast decision tools"
    )