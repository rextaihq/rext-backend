"""Strongly typed models for the Image Planning Pipeline."""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ContentType(str, Enum):
    """Canonical content types aligned with CONTENT_TYPE_TO_GENERATED_MODEL.

    Values use snake_case internally; kebab-case aliases are normalized
    in content_type_mapper.normalize_content_type.
    """

    # Informational
    BLOG = "blog"
    HOW_TO_GUIDE = "how_to_guide"
    EXPLAINER = "explainer"
    PILLAR_CONTENT = "pillar_content"
    CHECKLIST = "checklist"
    TUTORIAL = "tutorial"
    FAQ = "faq"
    WHITEPAPER = "whitepaper"
    CASE_STUDY = "case_study"
    GLOSSARY = "glossary"
    RESOURCE_LIST = "resource_list"
    NEWS = "news"  # design-system only; not a Rext generated model

    # Commercial
    COMPARISON = "comparison"
    BEST_TOOLS = "best_tools"
    ALTERNATIVES = "alternatives"
    PRODUCT_REVIEW = "product_review"  # in-depth-review
    PROS_CONS = "pros_cons"
    PRODUCT_ROUNDUP = "product_roundup"
    BUYING_GUIDE = "buying_guide"

    # Navigational
    BRAND_PAGE = "brand_page"
    PRODUCT_HOMEPAGE = "product_homepage"
    FEATURE_OVERVIEW = "feature_overview"
    DOCUMENTATION = "documentation"
    LOGIN_GUIDE = "login_guide"
    CONTACT_US = "contact_us"
    ABOUT_US = "about_us"
    HELP_CENTER = "help_center"

    # Transactional
    SALES_PAGE = "sales_page"
    PRICING_PAGE = "pricing_page"
    SIGNUP_PAGE = "signup_page"
    DEMO_PAGE = "demo_page"
    COUPON_PAGE = "coupon_page"
    CHECKOUT_PAGE = "checkout_page"
    LANDING_PAGE = "landing_page"
    SERVICE_PAGE = "service_page"


class SearchIntent(str, Enum):
    INFORMATIONAL = "informational"
    COMMERCIAL = "commercial"
    NAVIGATIONAL = "navigational"
    TRANSACTIONAL = "transactional"


class ImageGoal(str, Enum):
    ATTRACT_ATTENTION = "attract_attention"
    EXPLAIN_CONCEPT = "explain_concept"
    BUILD_TRUST = "build_trust"
    SHOWCASE_PRODUCT = "showcase_product"
    GUIDE_PROCESS = "guide_process"
    SUPPORT_NARRATIVE = "support_narrative"
    DRIVE_CONVERSION = "drive_conversion"


class ImageIntent(str, Enum):
    HERO = "hero"
    INLINE = "inline"
    FEATURED = "featured"
    SOCIAL = "social"
    THUMBNAIL = "thumbnail"


class ImageType(str, Enum):
    EDITORIAL_HERO = "editorial_hero_illustration"
    WORKFLOW = "workflow_illustration"
    PROCESS = "organized_process_illustration"
    BUSINESS_PHOTO = "real_business_photography"
    EXECUTIVE_MINIMAL = "minimal_executive_illustration"
    SPLIT_LAYOUT = "split_layout"
    HERO_MARKETING = "hero_marketing_illustration"
    TECHNICAL = "technical_illustration"
    CONCEPT = "concept_illustration"
    EDITORIAL_PHOTO = "editorial_photography"
    FRIENDLY_MINIMAL = "friendly_minimal_illustration"
    HUMAN_CENTRIC = "human_centric_illustration"
    PRODUCT_SHOWCASE = "product_showcase"
    PRODUCT_GRID = "product_grid_illustration"
    COMPARISON_ROUNDUP = "comparison_roundup_illustration"
    BRAND_IDENTITY = "brand_identity_illustration"
    FEATURE_HIGHLIGHT = "feature_highlight_illustration"
    CONVERSION_HERO = "conversion_hero_illustration"
    PRICING_VISUAL = "pricing_visual_illustration"
    RESOURCE_COLLECTION = "resource_collection_illustration"


class RenderingStyle(str, Enum):
    PHOTOREALISTIC = "photorealistic"
    THREE_D_RENDER = "3d_render"
    EDITORIAL_ILLUSTRATION = "editorial_illustration"
    VECTOR_ILLUSTRATION = "vector_illustration"
    WATERCOLOR = "watercolor"
    MINIMAL = "minimal"
    ABSTRACT = "abstract"
    FLAT_ILLUSTRATION = "flat_illustration"
    ISOMETRIC = "isometric"
    BLUEPRINT = "blueprint"
    PRODUCT_SHOWCASE = "product_showcase"
    CINEMATIC = "cinematic"


class LightingStyle(str, Enum):
    STUDIO = "studio"
    NATURAL = "natural"
    VOLUMETRIC = "volumetric"
    HDR = "hdr"
    CYBER = "cyber"
    NEON = "neon"
    AMBIENT = "ambient"
    DRAMATIC = "dramatic"
    SOFT = "soft"


class CameraAngle(str, Enum):
    EYE_LEVEL = "eye_level"
    WIDE = "wide"
    TOP_DOWN = "top_down"
    ISOMETRIC = "isometric"
    DRONE = "drone"
    CLOSE_UP = "close_up"
    MACRO = "macro"
    ARCHITECTURAL = "architectural"


class BrandStyle(str, Enum):
    PREMIUM_SAAS = "premium_saas"
    STARTUP = "startup"
    LUXURY = "luxury"
    DEVELOPER = "developer"
    CORPORATE = "corporate"
    FRIENDLY = "friendly"
    EDITORIAL = "editorial"


class Industry(str, Enum):
    TECHNOLOGY = "technology"
    HEALTHCARE = "healthcare"
    EDUCATION = "education"
    FINANCE = "finance"
    MARKETING = "marketing"
    BUSINESS = "business"
    FOOD = "food"
    MEDICAL = "medical"
    GENERAL = "general"


class AspectRatio(str, Enum):
    SQUARE = "1:1"
    LANDSCAPE = "16:9"
    PORTRAIT = "9:16"
    WIDE = "3:2"
    STANDARD = "4:3"


class ImageOrientation(str, Enum):
    LANDSCAPE = "landscape"
    PORTRAIT = "portrait"
    SQUARE = "square"


class CompositionStyle(str, Enum):
    RULE_OF_THIRDS = "rule_of_thirds"
    CENTERED = "centered"
    SYMMETRICAL = "symmetrical"
    ASYMMETRICAL = "asymmetrical"
    SPLIT = "split"
    LEADING_LINES = "leading_lines"
    NEGATIVE_SPACE_HEAVY = "negative_space_heavy"
    LAYERED_DEPTH = "layered_depth"
    WIDE_CINEMATIC = "wide_cinematic"


# ---------------------------------------------------------------------------
# Input
# ---------------------------------------------------------------------------


class ProductInfo(BaseModel):
    """Optional product context for product-led imagery."""

    name: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None
    key_features: list[str] = Field(default_factory=list)
    visual_cues: list[str] = Field(default_factory=list)


class ArticleImageInput(BaseModel):
    """Article metadata consumed by the Image Planner."""

    title: str = Field(..., description="Article title")
    summary: str = Field(
        default="",
        description="Short article summary or brief",
    )
    content_type: ContentType = ContentType.BLOG
    search_intent: SearchIntent = SearchIntent.INFORMATIONAL
    primary_keyword: str = ""
    secondary_keywords: list[str] = Field(default_factory=list)
    audience: list[str] = Field(default_factory=list)
    brand_voice: str = ""
    writing_style: str = ""
    product: Optional[ProductInfo] = None
    industry_hint: Optional[str] = None


# ---------------------------------------------------------------------------
# Planning / Art Direction
# ---------------------------------------------------------------------------


class ColorPalette(BaseModel):
    """Resolved color direction for the image."""

    name: str = "technology"
    primary: str = "blue"
    secondary: Optional[str] = "cyan"
    accent: Optional[str] = "purple"
    background: Optional[str] = "dark navy"
    harmony: str = "analogous"


class CompositionDirection(BaseModel):
    """Composition choices made by the Art Director."""

    style: CompositionStyle = CompositionStyle.WIDE_CINEMATIC
    framing: str = "wide establishing frame"
    balance: str = "asymmetrical with left-weighted subject"
    symmetry: str = "intentional asymmetry"
    rule_of_thirds: bool = True
    leading_lines: str = "subtle converging lines toward focal point"
    spacing: str = "generous breathing room around primary subject"
    depth: str = "clear foreground, midground, and soft background layers"
    contrast: str = "high subject-to-background contrast"
    color_harmony: str = "restrained complementary accents"
    typography_space: str = "upper-left negative space for title overlay"
    visual_hierarchy: str = "primary subject dominates; supports stay quiet"


class FocusLayers(BaseModel):
    """Spatial and narrative focus layers."""

    primary_focus: str
    secondary_focus: str = ""
    supporting_elements: list[str] = Field(default_factory=list)
    background: str = ""
    foreground: str = ""
    negative_space: str = "approximately 35-40 percent reserved for overlay"


class ArtDirection(BaseModel):
    """Enriched creative direction produced by the Art Director."""

    composition: CompositionDirection = Field(default_factory=CompositionDirection)
    focus: FocusLayers
    rendering_style: RenderingStyle = RenderingStyle.EDITORIAL_ILLUSTRATION
    lighting: LightingStyle = LightingStyle.VOLUMETRIC
    camera: CameraAngle = CameraAngle.WIDE
    color_palette: ColorPalette = Field(default_factory=ColorPalette)
    brand_style: BrandStyle = BrandStyle.PREMIUM_SAAS
    design_language: list[str] = Field(default_factory=list)
    mood: list[str] = Field(default_factory=list)
    industry: Industry = Industry.TECHNOLOGY


class ImagePlanningContext(BaseModel):
    """Complete planning brief used by prompt composers."""

    image_goal: ImageGoal = ImageGoal.ATTRACT_ATTENTION
    communication_goal: str = ""
    image_intent: ImageIntent = ImageIntent.FEATURED
    image_type: ImageType = ImageType.EDITORIAL_HERO
    audience: list[str] = Field(default_factory=list)
    visual_story: str = ""
    primary_subject: str = ""
    supporting_subjects: list[str] = Field(default_factory=list)
    environment: str = ""
    composition: str = ""
    visual_hierarchy: str = ""
    focal_point: str = ""
    camera_angle: CameraAngle = CameraAngle.WIDE
    perspective: str = "slightly elevated wide perspective"
    depth: str = "layered depth with soft background falloff"
    negative_space: str = "upper-left negative space for title overlay"
    lighting: LightingStyle = LightingStyle.SOFT
    color_palette: ColorPalette = Field(default_factory=ColorPalette)
    rendering_style: RenderingStyle = RenderingStyle.EDITORIAL_ILLUSTRATION
    design_language: list[str] = Field(default_factory=list)
    mood: list[str] = Field(default_factory=list)
    branding_style: BrandStyle = BrandStyle.PREMIUM_SAAS
    aspect_ratio: AspectRatio = AspectRatio.LANDSCAPE
    image_orientation: ImageOrientation = ImageOrientation.LANDSCAPE
    objects_to_avoid: list[str] = Field(default_factory=list)
    negative_prompt: str = ""
    accessibility_considerations: list[str] = Field(default_factory=list)

    # Source metadata retained for composers
    content_type: ContentType = ContentType.BLOG
    search_intent: SearchIntent = SearchIntent.INFORMATIONAL
    primary_keyword: str = ""
    secondary_keywords: list[str] = Field(default_factory=list)
    title: str = ""
    summary: str = ""
    brand_voice: str = ""
    writing_style: str = ""
    industry: Industry = Industry.TECHNOLOGY
    product: Optional[ProductInfo] = None

    # Filled by Art Director
    art_direction: Optional[ArtDirection] = None


class ComposedImagePrompt(BaseModel):
    """Final model-agnostic prompt package."""

    prompt: str
    negative_prompt: str = ""
    planning_context: ImagePlanningContext
    aspect_ratio: AspectRatio = AspectRatio.LANDSCAPE
    recommended_size: str = "1792x1024"
    style_tags: list[str] = Field(default_factory=list)
    format_hint: str = "openai"  # openai | flux | midjourney | ideogram
