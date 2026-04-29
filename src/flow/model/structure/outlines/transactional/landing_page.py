# from typing import List, Optional
# from pydantic import Field
# from src.flow.model.structure.outlines.base import BaseOutline, Section


# class LandingPageOutline(BaseOutline):
#     """Outline for a specific lead-gen or offer-driven landing page."""
#     campaign_name: str = Field(description="The marketing campaign this belongs to.")
#     lead_magnet: Optional[str] = Field(description="What the user gets (e.g., 'Free Ebook', 'Newsletter').")
#     conversion_goal: str = Field(description="What action the user should take.")
#     hero_headline: str = Field(description="The main hook.")
#     benefits_highlighted: List[str] = Field(description="What to emphasize.")



from typing import List, Optional, Literal
from pydantic import BaseModel, Field


class HeroSection(BaseModel):
    headline: str = Field(description="Primary attention-grabbing headline (clear + benefit-driven).")
    subheadline: str = Field(description="Supporting message that clarifies value proposition.")
    primary_cta: str = Field(description="Main call-to-action text (e.g., 'Get Started Free').")
    secondary_cta: Optional[str] = Field(default=None, description="Optional secondary CTA (e.g., 'Watch Demo').")
    trust_signals: Optional[List[str]] = Field(default_factory=list, description="Logos, ratings, or quick credibility boosters.")


class ProblemSection(BaseModel):
    pain_points: List[str] = Field(description="Core problems the target audience is facing.")
    emotional_triggers: Optional[List[str]] = Field(default_factory=list, description="Frustrations, fears, or desires.")


class SolutionSection(BaseModel):
    solution_summary: str = Field(description="Clear explanation of how the product/service solves the problem.")
    unique_mechanism: Optional[str] = Field(default=None, description="What makes this solution different or better.")


class BenefitItem(BaseModel):
    benefit: str
    description: str


class BenefitsSection(BaseModel):
    benefits: List[BenefitItem]


class SocialProofSection(BaseModel):
    testimonials: List[str] = Field(description="Customer quotes or reviews.")
    case_study_snippets: Optional[List[str]] = Field(default_factory=list)
    metrics: Optional[List[str]] = Field(default_factory=list, description="Quantifiable proof (e.g., '10,000+ users').")


class OfferSection(BaseModel):
    offer_summary: str = Field(description="What exactly the user gets.")
    pricing_info: Optional[str] = Field(default=None)
    bonuses: Optional[List[str]] = Field(default_factory=list)
    guarantee: Optional[str] = Field(default=None, description="Risk reversal (e.g., money-back guarantee).")


class ObjectionHandlingSection(BaseModel):
    common_objections: List[str] = Field(description="Typical user doubts.")
    responses: List[str] = Field(description="Clear responses to overcome objections.")


class FAQItem(BaseModel):
    question: str
    answer: str


class FAQSection(BaseModel):
    faqs: List[FAQItem]


class CTASection(BaseModel):
    primary_cta: str
    urgency: Optional[str] = Field(default=None, description="Scarcity or urgency (e.g., limited time).")
    reinforcement: Optional[str] = Field(default=None, description="Final persuasion line.")


class LandingPageOutline(BaseModel):
    # Core SEO + Strategy
    title: str
    slug_suggestion: str = Field(pattern=r"^[a-z0-9-]+$")
    focus_keyphrase: str
    target_audience: List[str]
    tone: Literal[
        "Professional", "Conversational", "Persuasive", "Friendly",
        "Direct", "Action-oriented", "Urgent", "Trustworthy"
    ]

    # Campaign Context
    campaign_name: str
    conversion_goal: str = Field(description="Exact action user should take (signup, book demo, etc.)")
    traffic_source: Optional[str] = Field(default=None, description="Ads, organic, email, etc.")

    # Page Structure (Conversion Flow)
    hero: HeroSection
    problem: ProblemSection
    solution: SolutionSection
    benefits: BenefitsSection
    social_proof: SocialProofSection
    offer: OfferSection
    objection_handling: ObjectionHandlingSection
    faq: Optional[FAQSection] = None
    final_cta: CTASection

    # Optional Enhancers
    lead_magnet: Optional[str] = Field(default=None)
    visual_direction: Optional[List[str]] = Field(
        default_factory=list,
        description="Image or design suggestions (e.g., product UI, happy users, charts)."
    )

    # Length Control
    target_word_count: int = Field(ge=300, le=2000)