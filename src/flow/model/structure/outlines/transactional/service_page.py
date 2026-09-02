# from typing import List, Optional
# from pydantic import Field
# from src.flow.model.structure.outlines.base import BaseOutline, Section


# class ServicePageOutline(BaseOutline):
#     """Outline for a local business or agency service page."""
#     service_name: str = Field(description="What is being provided (e.g., 'Plumbing', 'SEO Consulting').")
#     service_area: Optional[str] = Field(description="Locations covered, if local.")
#     the_process: List[str] = Field(description="How the service works, step-by-step.")
#     why_choose_us: List[str] = Field(description="Differentiators or selling points.")


from typing import List, Literal, Optional

from pydantic import BaseModel, Field

# -------------------------
# HERO SECTION (CLARITY + POSITIONING)
# -------------------------


class ServiceHero(BaseModel):
    headline: str = Field(description="Clear service value proposition (not vague marketing)")
    subheadline: str = Field(description="Explains who it is for + outcome")

    primary_cta: str = Field(description="e.g., 'Get a Free Consultation', 'Book a Call'")
    secondary_cta: Optional[str] = None

    trust_signals: Optional[List[str]] = Field(
        default_factory=list, description="Certifications, years of experience, ratings, logos"
    )


# -------------------------
# SERVICE DEFINITION
# -------------------------


class ServiceOverview(BaseModel):
    service_name: str
    description: str = Field(description="What the service actually does in simple terms")

    who_it_is_for: List[str]
    who_it_is_not_for: Optional[List[str]] = Field(default_factory=list)


# -------------------------
# PROBLEM → CONTEXT
# -------------------------


class ProblemContext(BaseModel):
    pain_points: List[str]
    consequences: Optional[List[str]] = Field(
        default_factory=list, description="What happens if the problem is not solved"
    )


# -------------------------
# SOLUTION (SERVICE DELIVERY)
# -------------------------


class ServiceProcessStep(BaseModel):
    step: str
    description: str


class ServiceSolution(BaseModel):
    approach_summary: str
    methodology: Optional[str] = Field(
        default=None, description="How the service is delivered (framework/system)"
    )

    process: List[ServiceProcessStep]


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
    case_studies: Optional[List[str]] = Field(default_factory=list)
    metrics: Optional[List[str]] = Field(
        default_factory=list, description="Results like ROI, time saved, revenue growth"
    )
    client_logos: Optional[List[str]] = Field(default_factory=list)


# -------------------------
# PRICING / ESTIMATION (SERVICE-SPECIFIC)
# -------------------------


class PricingSection(BaseModel):
    pricing_model: Literal["fixed", "hourly", "custom_quote", "retainer", "tiered"]

    starting_price: Optional[str]
    price_range: Optional[str]

    includes: List[str]
    excludes: Optional[List[str]] = Field(default_factory=list)


# -------------------------
# OBJECTION HANDLING
# -------------------------


class Objection(BaseModel):
    concern: str
    response: str


class ObjectionHandling(BaseModel):
    objections: List[Objection]


# -------------------------
# LEAD QUALIFICATION (IMPORTANT FOR SERVICES)
# -------------------------


class QualificationCriteria(BaseModel):
    ideal_client_traits: List[str]
    disqualifiers: Optional[List[str]] = Field(default_factory=list)
    required_budget_range: Optional[str] = None


# -------------------------
# CTA SYSTEM
# -------------------------


class CTASection(BaseModel):
    primary_cta: str
    secondary_cta: Optional[str] = None
    reinforcement_message: Optional[str] = Field(
        default=None, description="Final persuasive line before CTA"
    )


# -------------------------
# FAQ (CONVERSION-FOCUSED)
# -------------------------


class FAQItem(BaseModel):
    question: str
    answer: str


class FAQSection(BaseModel):
    faqs: List[FAQItem]


# -------------------------
# FINAL SERVICE PAGE SCHEMA
# -------------------------


class ServicePageOutline(BaseModel):
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
        "Professional", "Trustworthy", "Conversational", "Direct", "Persuasive", "Action-oriented"
    ]

    # Conversion Goal
    conversion_goal: Literal[
        "book_consultation", "request_quote", "schedule_call", "contact_us", "start_service"
    ]

    # Page Structure (Service Conversion Flow)
    hero: ServiceHero
    service_overview: ServiceOverview
    problem_context: ProblemContext
    solution: ServiceSolution
    benefits: BenefitsSection
    social_proof: SocialProof
    pricing: Optional[PricingSection]
    objection_handling: ObjectionHandling
    qualification: QualificationCriteria

    # FAQ layer (service-specific questions before booking/quote)
    faq: Optional[FAQSection] = None

    # CTA Layer
    cta: CTASection

    # Optional Enhancers (modern CRO)
    urgency_elements: Optional[List[str]] = Field(
        default_factory=list, description="Limited slots, booking deadlines, seasonal availability"
    )

    lead_magnet: Optional[str] = Field(
        default=None, description="Optional free audit, checklist, or consultation offer"
    )

    # Optimization
    target_word_count: int = Field(
        default=900, ge=500, le=3000, description="Service pages are medium-length conversion pages"
    )
