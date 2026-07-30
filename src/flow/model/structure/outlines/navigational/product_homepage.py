# 
from typing import List, Optional, Literal
from pydantic import BaseModel, Field


# -------------------------
# HERO (PRODUCT POSITIONING)
# -------------------------

class ProductHero(BaseModel):
    product_name: str
    headline: str = Field(description="Core value proposition in one sentence")
    subheadline: str = Field(description="Explains what the product does and for whom")

    primary_cta: str = Field(description="e.g., 'Start Free Trial', 'Get Started'")
    secondary_cta: Optional[str] = Field(default=None)

    demo_available: Optional[bool] = True
    interactive_demo: Optional[bool] = False


# -------------------------
# VALUE PROPOSITION (WHY THIS PRODUCT EXISTS)
# -------------------------

class ValueProposition(BaseModel):
    problem_solved: str
    core_benefit: str
    unique_differentiation: str


# -------------------------
# FEATURE DISCOVERY (CORE OF PRODUCT HOMEPAGE)
# -------------------------

class FeatureItem(BaseModel):
    name: str
    description: str
    link: Optional[str]


class FeatureSection(BaseModel):
    features: List[FeatureItem]


# -------------------------
# USE CASES (REAL WORLD APPLICATIONS)
# -------------------------

class UseCase(BaseModel):
    scenario: str
    outcome: str


class UseCaseSection(BaseModel):
    use_cases: List[UseCase]


# -------------------------
# HOW IT WORKS (SIMPLIFIED PRODUCT FLOW)
# -------------------------

class Step(BaseModel):
    step: str
    description: str


class HowItWorks(BaseModel):
    steps: List[Step]


# -------------------------
# PRODUCT ECOSYSTEM (INTEGRATIONS + PLATFORM THINKING)
# -------------------------

class Integration(BaseModel):
    name: str
    description: Optional[str]
    link: Optional[str]


class Ecosystem(BaseModel):
    integrations: List[Integration]
    api_available: Optional[bool]
    sdk_supported: Optional[List[str]]


# -------------------------
# SOCIAL PROOF (TRUST ENGINE)
# -------------------------

class SocialProof(BaseModel):
    user_metrics: List[str] = Field(description="e.g., users, revenue, usage stats")
    testimonials: Optional[List[str]] = Field(default_factory=list)
    client_logos: Optional[List[str]] = Field(default_factory=list)
    case_studies: Optional[List[str]] = Field(default_factory=list)


# -------------------------
# PRODUCT COMPARISON (POSITIONING CONTEXT)
# -------------------------

class Comparison(BaseModel):
    compared_to: str
    advantages: List[str]


# -------------------------
# ONBOARDING / ACTIVATION FLOW
# -------------------------

class ActivationFlow(BaseModel):
    steps_to_first_value: List[str]
    time_to_value: Optional[str]
    onboarding_hint: Optional[str]


# -------------------------
# TRUST & SECURITY
# -------------------------

class TrustSignals(BaseModel):
    security_features: List[str]
    compliance: Optional[List[str]] = Field(default_factory=list)
    uptime: Optional[str]
    reliability_metrics: Optional[List[str]] = Field(default_factory=list)


# -------------------------
# PRICING PREVIEW (LIGHTWEIGHT ON HOMEPAGE)
# -------------------------

class PricingPreview(BaseModel):
    starting_price: Optional[str]
    pricing_model: Optional[Literal[
        "free", "freemium", "subscription", "usage-based", "enterprise"
    ]]
    link_to_pricing: Optional[str]


# -------------------------
# FAQ (PRODUCT-SPECIFIC QUESTIONS)
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
        default=None,
        description="e.g., 'No credit card required'"
    )


# -------------------------
# FINAL PRODUCT HOMEPAGE SCHEMA
# -------------------------

class ProductHomepageOutline(BaseModel):
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
        "Product-focused", "Clear", "Conversational",
        "Professional", "Action-oriented", "Trustworthy"
    ]

    # Core structure (product understanding flow)
    hero: ProductHero
    value_proposition: ValueProposition

    # Discovery layers
    features: FeatureSection
    use_cases: UseCaseSection
    how_it_works: HowItWorks

    # Ecosystem layer
    ecosystem: Ecosystem

    # Trust layer
    social_proof: SocialProof
    trust: TrustSignals

    # Positioning context
    comparison: Optional[Comparison]

    # Activation system (VERY IMPORTANT)
    activation_flow: ActivationFlow

    # Pricing preview (light exposure)
    pricing_preview: Optional[PricingPreview]

    # FAQ layer (common product/adoption questions before conversion)
    faq: Optional[FAQSection] = None

    # CTA layer
    cta: CTASection

    # Optimization Layer (2026 PLG standard)
    product_adoption_goal: str = Field(
        description="Primary goal (e.g., 'activate new users within 5 minutes')"
    )

    time_to_first_value_seconds: Optional[int] = Field(
        default=180,
        description="Time to first meaningful product success"
    )

    exploration_depth_target: Optional[Literal[
        "low", "medium", "high"
    ]]

    target_word_count: int = Field(
        default=1000,
        ge=500,
        le=3500,
        description="Product homepages are medium-depth discovery pages"
    )