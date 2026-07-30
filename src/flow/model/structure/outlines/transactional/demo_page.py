# from typing import List, Optional
# from pydantic import Field
# from src.flow.model.structure.outlines.base import BaseOutline, Section


# class DemoPageOutline(BaseOutline):
#     """Outline for a 'Book a Demo' or 'Request Demo' page."""
#     product_name: str = Field(description="The enterprise or complex product.")
#     booking_tool_integration: str = Field(description="E.g., 'Calendly', 'HubSpot'.")
#     what_to_expect: List[str] = Field(description="What happens during the demo call.")
#     qualifying_questions: Optional[List[str]] = Field(description="Questions asked in the form.")


from typing import List, Optional, Literal
from pydantic import BaseModel, Field


# -------------------------
# Hero Section (First Impression)
# -------------------------

class DemoHeroSection(BaseModel):
    headline: str = Field(description="Clear value-driven hook (e.g., 'See AI automation in action in 2 minutes')")
    subheadline: str = Field(description="What user will experience in the demo")
    
    primary_cta: str = Field(description="e.g., 'Start Demo', 'Book Live Demo', 'Try Interactive Demo'")
    secondary_cta: Optional[str] = Field(default=None)
    
    trust_signals: Optional[List[str]] = Field(
        default_factory=list,
        description="Logos, ratings, security badges"
    )


# -------------------------
# Demo Type Definition
# -------------------------

class DemoExperience(BaseModel):
    demo_type: Literal[
        "interactive",      # self-guided product tour
        "video",            # pre-recorded demo
        "live",             # sales-led demo
        "guided",           # step-by-step walkthrough
        "sandbox"           # hands-on environment
    ]
    
    duration: Optional[str] = Field(description="e.g., '2 minutes', '15 minutes'")
    
    access_method: Literal[
        "instant", "signup_required", "email_required", "calendar_booking"
    ]
    
    key_highlights: List[str]


# -------------------------
# Problem → Context Layer
# -------------------------

class ProblemContext(BaseModel):
    pain_points: List[str]
    triggers: Optional[List[str]] = Field(
        default_factory=list,
        description="Situations where users need the product"
    )


# -------------------------
# What Users Will See in Demo
# -------------------------

class DemoWalkthroughStep(BaseModel):
    step_title: str
    description: str
    visual_focus: Optional[str] = Field(
        default=None,
        description="UI area or feature shown in this step"
    )


class DemoWalkthrough(BaseModel):
    steps: List[DemoWalkthroughStep]


# -------------------------
# Value Reinforcement
# -------------------------

class ValueProof(BaseModel):
    key_benefits: List[str]
    time_to_value: Optional[str] = Field(description="How fast user sees value (e.g., 'Under 5 minutes')")
    roi_indicators: Optional[List[str]] = Field(default_factory=list)


# -------------------------
# Social Proof Layer
# -------------------------

class SocialProof(BaseModel):
    testimonials: List[str]
    customer_logos: Optional[List[str]] = Field(default_factory=list)
    metrics: Optional[List[str]] = Field(default_factory=list)


# -------------------------
# Conversion Layer
# -------------------------

class DemoCTA(BaseModel):
    primary_cta: str
    booking_steps: Optional[List[str]] = Field(
        default_factory=list,
        description="Only if live demo (e.g., select time → confirm email)"
    )
    friction_notes: Optional[List[str]] = Field(
        default_factory=list,
        description="Anything that might slow conversion (kept for optimization)"
    )


# -------------------------
# Objection Handling
# -------------------------

class ObjectionHandling(BaseModel):
    objections: List[str]
    responses: List[str]


# -------------------------
# FAQ (DEMO-SPECIFIC QUESTIONS)
# -------------------------

class FAQItem(BaseModel):
    question: str
    answer: str


class FAQSection(BaseModel):
    faqs: List[FAQItem]


# -------------------------
# Final Schema
# -------------------------

class DemoPageOutline(BaseModel):
    # SEO + Metadata
    title: str
    slug_suggestion: str = Field(pattern=r"^[a-z0-9-]+$")
    focus_keyphrase: str
    keywords_to_include: List[str] = Field(
        default_factory=list,
        description="Secondary and long-tail keywords to naturally incorporate throughout the page."
    )
    target_audience: List[str]
    tone: Literal[
        "Persuasive", "Trustworthy", "Professional",
        "Conversational", "Direct", "Action-oriented"
    ]

    # Core Conversion Intent
    conversion_goal: Literal[
        "book_demo",
        "start_trial",
        "try_interactive_demo",
        "request_sales_call"
    ]

    # Demo Experience
    demo_experience: DemoExperience

    # Page Structure (Conversion Flow)
    hero: DemoHeroSection
    problem_context: ProblemContext
    walkthrough: DemoWalkthrough
    value_proof: ValueProof
    social_proof: SocialProof
    objection_handling: ObjectionHandling
    faq: Optional[FAQSection] = None
    cta: DemoCTA

    # Optional Enhancers
    lead_capture_fields: Optional[List[str]] = Field(
        default_factory=list,
        description="Fields like name, email, company"
    )

    calendar_integration: Optional[bool] = Field(
        default=False,
        description="If demo booking is calendar-based"
    )

    # Optimization
    target_time_to_conversion_seconds: Optional[int] = Field(
        default=300,
        description="Ideal time to conversion (UX optimization metric)"
    )