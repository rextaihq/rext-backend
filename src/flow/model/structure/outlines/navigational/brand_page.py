# from typing import List, Optional
# from pydantic import Field
# from src.flow.model.structure.outlines.base import BaseOutline, Section


# class BrandPageOutline(BaseOutline):
#     """Outline for a brand's central informational page."""
#     brand_name: str = Field(description="The name of the brand.")
#     core_values: List[str] = Field(description="The core values or mission of the brand.")
#     founding_year: Optional[int] = Field(description="Year the brand was founded.")
#     key_products_or_services: List[str] = Field(description="Main offerings by this brand.")

from typing import List, Literal, Optional

from pydantic import BaseModel, Field

# -------------------------
# HERO / BRAND IDENTITY
# -------------------------


class BrandHero(BaseModel):
    brand_name: str
    tagline: str = Field(description="Short brand positioning statement")

    headline: str = Field(description="Core identity message (what the brand stands for)")
    subheadline: str = Field(description="Expanded value proposition")

    primary_cta: Optional[str] = Field(
        default="Explore Products", description="Soft navigation CTA"
    )


# -------------------------
# BRAND POSITIONING
# -------------------------


class BrandPositioning(BaseModel):
    mission: str
    vision: Optional[str]

    value_proposition: str
    category_definition: str = Field(description="How the brand defines its space in the market")


# -------------------------
# PRODUCT / ECOSYSTEM MAP
# -------------------------


class ProductItem(BaseModel):
    name: str
    description: str
    category: Optional[str]
    link: Optional[str]


class EcosystemMap(BaseModel):
    products: List[ProductItem]
    services: Optional[List[str]] = Field(default_factory=list)
    platforms: Optional[List[str]] = Field(default_factory=list)
    integrations: Optional[List[str]] = Field(default_factory=list)


# -------------------------
# BRAND DIFFERENTIATION
# -------------------------


class Differentiation(BaseModel):
    unique_selling_points: List[str]
    competitive_advantages: Optional[List[str]] = Field(default_factory=list)
    innovation_focus: Optional[str] = None


# -------------------------
# TRUST LAYER (CRITICAL IN 2026)
# -------------------------


class TrustSignals(BaseModel):
    metrics: List[str] = Field(description="Scale indicators (users, revenue, countries, etc.)")
    client_logos: Optional[List[str]] = Field(default_factory=list)
    awards: Optional[List[str]] = Field(default_factory=list)
    press_mentions: Optional[List[str]] = Field(default_factory=list)
    certifications: Optional[List[str]] = Field(default_factory=list)


# -------------------------
# BRAND STORY (LIGHTWEIGHT)
# -------------------------


class BrandStory(BaseModel):
    origin: str
    journey_highlights: List[str]
    turning_points: Optional[List[str]] = Field(default_factory=list)


# -------------------------
# AUDIENCE MAPPING
# -------------------------


class AudienceSegment(BaseModel):
    segment: str
    needs: List[str]
    solutions_offered: List[str]


class AudienceMap(BaseModel):
    segments: List[AudienceSegment]


# -------------------------
# NAVIGATION HUB (KEY PURPOSE OF BRAND PAGE)
# -------------------------


class NavigationHub(BaseModel):
    primary_paths: List[str] = Field(description="Key routes like Products, Pricing, Docs, Contact")
    secondary_paths: Optional[List[str]] = Field(default_factory=list)
    recommended_journeys: Optional[List[str]] = Field(
        default_factory=list,
        description="Suggested user flows (e.g., 'Start free trial → Explore features → Book demo')",
    )


# -------------------------
# SOCIAL PROOF
# -------------------------


class SocialProof(BaseModel):
    testimonials: List[str]
    case_studies: Optional[List[str]] = Field(default_factory=list)
    user_metrics: Optional[List[str]] = Field(default_factory=list)


# -------------------------
# VALUES / CULTURE
# -------------------------


class ValuesSection(BaseModel):
    values: List[str]
    principles: Optional[List[str]] = Field(default_factory=list)


# -------------------------
# CTA SYSTEM (SOFT NAVIGATION)
# -------------------------


class CTASection(BaseModel):
    primary_cta: str
    secondary_cta: Optional[str] = None
    guidance_text: Optional[str] = Field(
        default=None, description="Soft guidance like 'Choose what fits you best'"
    )


# -------------------------
# FINAL BRAND PAGE SCHEMA
# -------------------------


class BrandPageOutline(BaseModel):
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
        "Professional", "Trustworthy", "Inspirational", "Conversational", "Neutral", "Authoritative"
    ]

    # Core Brand Structure
    hero: BrandHero
    positioning: BrandPositioning
    story: BrandStory

    # Ecosystem Layer (VERY IMPORTANT)
    ecosystem: EcosystemMap
    navigation: NavigationHub

    # Differentiation + Trust
    differentiation: Differentiation
    trust: TrustSignals
    social_proof: SocialProof

    # Audience mapping
    audience_map: AudienceMap

    # Values
    values: ValuesSection

    # CTA (light navigation intent)
    cta: CTASection

    # Optimization Layer (2026 UX behavior)
    exploration_intent_level: Literal[
        "low",  # curiosity browsing
        "medium",  # comparing brands
        "high",  # ready to explore products
    ]

    brand_type: Literal[
        "single_product", "multi_product", "platform", "ecosystem", "enterprise_suite"
    ]

    target_word_count: int = Field(
        default=900, ge=500, le=2500, description="Brand pages are medium-depth navigation pages"
    )
