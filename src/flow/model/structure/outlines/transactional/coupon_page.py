# from typing import List, Optional
# from pydantic import Field
# from src.flow.model.structure.outlines.base import BaseOutline, Section


# class CouponPageOutline(BaseOutline):
#     """Outline for a discount, promo code, or coupon page."""
#     brand_or_product: str = Field(description="The brand offering the discount.")
#     offer_details: str = Field(description="What the actual discount is (e.g., '20% Off').")
#     expiration_date: Optional[str] = Field(description="When the offer ends.")
#     terms_and_conditions: List[str] = Field(description="Restrictions on the coupon.")


from typing import List, Optional, Literal
from pydantic import BaseModel, Field


# -------------------------
# Core Offer Definition
# -------------------------

class CouponOffer(BaseModel):
    title: str = Field(description="Short offer headline (e.g., '20% OFF Sitewide')")
    description: str = Field(description="Clear explanation of discount")
    discount_type: Literal["percentage", "fixed", "free_shipping", "bundle", "bogo"]
    discount_value: Optional[str] = Field(
        default=None,
        description="e.g., '20%', '$10', 'Free Shipping'"
    )
    applicable_products: Optional[List[str]] = Field(
        default_factory=list,
        description="What the coupon applies to"
    )


# -------------------------
# Coupon Mechanics
# -------------------------

class CouponDetails(BaseModel):
    code: str = Field(description="The actual coupon code")
    expiry_date: Optional[str]
    usage_limit: Optional[int] = Field(description="Max number of uses")
    minimum_purchase: Optional[str] = Field(description="Minimum cart value")
    stackable: bool = Field(default=False, description="Can combine with other offers")


# -------------------------
# Redemption Flow
# -------------------------

class RedemptionFlow(BaseModel):
    steps: List[str] = Field(
        description="Simple steps like: Copy code → Add to cart → Apply at checkout"
    )
    auto_apply: bool = Field(
        default=False,
        description="Whether coupon is automatically applied"
    )


# -------------------------
# Trust & Urgency
# -------------------------

class TrustAndUrgency(BaseModel):
    trust_signals: List[str] = Field(
        description="Security, verified deal, brand credibility"
    )
    urgency_triggers: Optional[List[str]] = Field(
        default_factory=list,
        description="e.g., 'Limited time offer', 'Only 100 uses left'"
    )
    social_proof: Optional[List[str]] = Field(
        default_factory=list,
        description="User claims, ratings, usage stats"
    )


# -------------------------
# UI / UX Copy Layer
# -------------------------

class CouponUIMicrocopy(BaseModel):
    copy_button_text: str = Field(default="Copy Code")
    success_message: str = Field(default="Code copied successfully!")
    apply_instructions: str = Field(
        description="Short instruction like 'Paste this at checkout'"
    )


# -------------------------
# Conversion CTA
# -------------------------

class CTASection(BaseModel):
    primary_cta: str = Field(description="e.g., 'Shop Now & Save'")
    secondary_cta: Optional[str] = Field(default=None)


# -------------------------
# MAIN SCHEMA
# -------------------------

class CouponPageOutline(BaseModel):
    # Metadata
    title: str
    slug_suggestion: str = Field(pattern=r"^[a-z0-9-]+$")
    focus_keyphrase: str
    target_audience: List[str]
    tone: Literal[
        "Persuasive", "Urgent", "Friendly", "Direct", "Trustworthy"
    ]

    # Offer Layer
    coupon_offer: CouponOffer
    coupon_details: CouponDetails

    # Conversion Flow
    redemption_flow: RedemptionFlow

    # Trust Layer
    trust_urgency: TrustAndUrgency

    # UX Layer
    ui_microcopy: CouponUIMicrocopy

    # CTA
    cta: CTASection

    # Optional Enhancers
    supported_devices: Optional[List[str]] = Field(
        default_factory=list,
        description="e.g., Web, Mobile App"
    )
    
    affiliate_disclosure: Optional[str] = Field(
        default=None,
        description="If applicable (important for SEO + compliance)"
    )