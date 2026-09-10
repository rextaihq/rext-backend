# from typing import List, Optional
# from pydantic import Field
# from src.flow.model.structure.outlines.base import BaseOutline, Section


# class PricingTier(Section):
#     """A section describing a specific pricing tier."""
#     tier_name: str = Field(description="E.g., 'Basic', 'Pro', 'Enterprise'.")
#     price_point: str = Field(description="E.g., '$29/mo' or 'Custom'.")
#     target_user: str = Field(description="Who this tier is best for.")


# class PricingPageOutline(BaseOutline):
#     """Outline for a pricing comparison page."""
#     product_name: str = Field(description="The product being priced.")
#     pricing_model: str = Field(description="E.g., 'Subscription', 'One-time', 'Usage-based'.")
#     has_free_tier: bool = Field(default=False)
#     sections: List[PricingTier] = Field(description="The pricing tiers detailed.")


from typing import List, Literal, Optional

from pydantic import BaseModel, Field

# -------------------------
# Pricing Plan Core
# -------------------------


class PricingFeature(BaseModel):
    feature: str
    included: bool = True
    limitation: Optional[str] = None


class PricingPlan(BaseModel):
    name: str = Field(description="Plan name (e.g., Starter, Pro, Enterprise)")
    price: str = Field(description="Formatted price (e.g., '$29/month')")
    billing_cycle: Literal["monthly", "yearly", "usage-based", "one-time"]

    description: str

    features: List[PricingFeature]

    is_popular: Optional[bool] = False

    cta_text: str = Field(default="Get Started")


# -------------------------
# Value Framing Layer
# -------------------------


class ValuePositioning(BaseModel):
    headline: str = Field(
        description="Pricing page core message (e.g., 'Simple pricing for every team')"
    )
    subheadline: str

    key_value_points: List[str]


# -------------------------
# Comparison Layer
# -------------------------


class PlanComparison(BaseModel):
    feature_name: str
    starter: Optional[str]
    pro: Optional[str]
    enterprise: Optional[str]


class ComparisonTable(BaseModel):
    rows: List[PlanComparison]


# -------------------------
# Billing & Pricing Logic
# -------------------------


class BillingOptions(BaseModel):
    monthly_available: bool = True
    yearly_discount_percentage: Optional[int]
    usage_based_model: Optional[str] = Field(
        default=None, description="Explanation of usage-based pricing if applicable"
    )
    free_trial_days: Optional[int]


# -------------------------
# Trust & Risk Reversal
# -------------------------


class TrustSignals(BaseModel):
    guarantees: List[str] = Field(description="Money-back guarantee, cancel anytime, etc.")
    security_badges: Optional[List[str]] = Field(default_factory=list)
    customer_logos: Optional[List[str]] = Field(default_factory=list)
    testimonials: Optional[List[str]] = Field(default_factory=list)


# -------------------------
# Objection Handling
# -------------------------


class Objection(BaseModel):
    question: str
    answer: str


class ObjectionHandling(BaseModel):
    objections: List[Objection]


# -------------------------
# Upgrade / Downgrade Strategy
# -------------------------


class PricingFlexibility(BaseModel):
    upgrade_path: str
    downgrade_policy: Optional[str]
    cancellation_policy: str


# -------------------------
# CTA Layer
# -------------------------


class PricingCTA(BaseModel):
    primary_cta: str = Field(description="e.g., 'Start Free Trial'")
    secondary_cta: Optional[str] = Field(default=None)

    urgency_message: Optional[str] = Field(
        default=None, description="e.g., 'No credit card required'"
    )


# -------------------------
# Final Schema
# -------------------------


class PricingPageOutline(BaseModel):
    # SEO + Metadata
    title: str
    slug_suggestion: str = Field(pattern=r"^[a-z0-9-]+$")
    focus_keyphrase: str
    keywords_to_include: List[str] = Field(
        default_factory=list,
        description="Secondary and long-tail keywords to naturally incorporate throughout the page.",
    )
    target_audience: List[str]
    tone: Literal["Professional", "Persuasive", "Trustworthy", "Direct", "Clear", "Action-oriented"]

    # Core Pricing Strategy
    value_positioning: ValuePositioning
    billing_options: BillingOptions

    # Plans
    pricing_plans: List[PricingPlan]

    # Comparison (critical for decision-making)
    comparison_table: Optional[ComparisonTable]

    # Conversion Psychology
    trust_signals: TrustSignals
    objection_handling: ObjectionHandling
    pricing_flexibility: PricingFlexibility

    # CTA Layer
    cta: PricingCTA

    # Optimization Layer
    currency: str = Field(description="ISO currency (USD, EUR, PKR, etc.)")
    pricing_strategy_type: Literal["flat_rate", "tiered", "freemium", "usage_based", "hybrid"]

    # Optional Enhancers
    faq: Optional[List[str]] = Field(default_factory=list)
    target_word_count: Optional[int] = Field(
        default=300, description="Pricing pages are micro-content, NOT long-form"
    )
