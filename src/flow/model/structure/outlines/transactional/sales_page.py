# from typing import List, Optional
# from pydantic import Field
# from src.flow.model.structure.outlines.base import BaseOutline, Section


# class SalesPageOutline(BaseOutline):
#     """Outline for a long-form or direct sales page."""
#     product_or_service: str = Field(description="What is being sold.")
#     main_pain_point_addressed: str = Field(description="The core problem the user has that this solves.")
#     urgency_or_scarcity_element: Optional[str] = Field(description="Why they should buy right now.")
#     guarantee_or_risk_reversal: Optional[str] = Field(description="Money-back guarantee, free trial, etc.")
#     primary_cta: str = Field(description="The primary button copy (e.g., 'Buy Now for $99').")

from typing import List, Optional, Literal
from pydantic import BaseModel, Field


# -------------------------
# HERO / FIRST IMPACT
# -------------------------

class SalesHero(BaseModel):
    headline: str = Field(description="High-impact benefit-driven hook")
    subheadline: str = Field(description="Clarifies offer in simple terms")
    
    primary_cta: str
    secondary_cta: Optional[str] = None
    
    hero_visual_direction: Optional[str] = Field(
        default=None,
        description="Image/video idea (product demo, transformation, etc.)"
    )


# -------------------------
# PROBLEM AGITATION
# -------------------------

class ProblemSection(BaseModel):
    pain_points: List[str]
    emotional_agitation: List[str] = Field(
        description="Amplifies frustration, fear, or missed opportunity"
    )
    consequences: Optional[List[str]] = None


# -------------------------
# SOLUTION POSITIONING
# -------------------------

class SolutionSection(BaseModel):
    solution_summary: str
    unique_mechanism: Optional[str] = Field(
        default=None,
        description="What makes this solution different"
    )
    why_now: Optional[str] = None


# -------------------------
# OFFER STRUCTURE
# -------------------------

class OfferInclusion(BaseModel):
    item: str
    value: Optional[str] = None


class OfferSection(BaseModel):
    offer_title: str
    inclusions: List[OfferInclusion]
    bonuses: Optional[List[str]] = []
    price: Optional[str] = None
    discount: Optional[str] = None
    guarantee: Optional[str] = Field(
        default=None,
        description="Risk reversal (e.g., 30-day money-back guarantee)"
    )


# -------------------------
# BENEFITS (OUTCOME-FOCUSED)
# -------------------------

class BenefitItem(BaseModel):
    benefit: str
    explanation: str


class BenefitsSection(BaseModel):
    benefits: List[BenefitItem]


# -------------------------
# SOCIAL PROOF (TRUST ENGINE)
# -------------------------

class SocialProof(BaseModel):
    testimonials: List[str]
    case_study_snippets: Optional[List[str]] = []
    metrics: Optional[List[str]] = Field(
        default_factory=list,
        description="Quantified proof like '10k+ users', '300% ROI'"
    )
    logos: Optional[List[str]] = []


# -------------------------
# OBJECTION HANDLING (CRITICAL IN 2026)
# -------------------------

class Objection(BaseModel):
    objection: str
    response: str


class ObjectionHandling(BaseModel):
    objections: List[Objection]


# -------------------------
# URGENCY & SCARCITY
# -------------------------

class UrgencySection(BaseModel):
    urgency_triggers: List[str] = Field(
        description="Limited time, limited seats, expiring offer"
    )
    scarcity_type: Optional[Literal["time", "stock", "bonus", "pricing"]] = None


# -------------------------
# CTA SYSTEM
# -------------------------

class CTASection(BaseModel):
    primary_cta: str
    repeated_ctas: Optional[List[str]] = Field(
        default_factory=list,
        description="CTAs placed across page sections"
    )
    reinforcement_line: Optional[str] = Field(
        default=None,
        description="Final persuasion sentence before CTA"
    )


# -------------------------
# FAQ (Conversion-Focused)
# -------------------------

class FAQItem(BaseModel):
    question: str
    answer: str


class FAQSection(BaseModel):
    faqs: List[FAQItem]


# -------------------------
# FINAL SALES PAGE SCHEMA
# -------------------------

class SalesPageOutline(BaseModel):
    # Core metadata
    title: str
    slug_suggestion: str = Field(pattern=r"^[a-z0-9-]+$")
    focus_keyphrase: str
    
    target_audience: List[str]
    tone: Literal[
        "Persuasive", "Urgent", "Direct",
        "Trustworthy", "Conversational", "Action-oriented"
    ]

    # Conversion Goal
    conversion_goal: Literal[
        "purchase",
        "subscribe",
        "book_call",
        "start_trial"
    ]

    # Page Flow (Psychological Structure)
    hero: SalesHero
    problem: ProblemSection
    solution: SolutionSection
    offer: OfferSection
    benefits: BenefitsSection
    social_proof: SocialProof
    objection_handling: ObjectionHandling
    urgency: UrgencySection
    faq: Optional[FAQSection]

    # Final Conversion Layer
    cta: CTASection

    # Optimization Layer (important in 2026 CRO systems)
    price_psychology_type: Optional[Literal[
        "anchoring",
        "decoy_effect",
        "bundling",
        "discount_framing",
        "value_stacking"
    ]]

    guarantee_type: Optional[Literal[
        "money_back",
        "free_trial",
        "cancel_anytime",
        "satisfaction_guarantee"
    ]]

    target_word_count: int = Field(
        default=1200,
        ge=600,
        le=4000,
        description="Sales pages are medium-length persuasion pages"
    )