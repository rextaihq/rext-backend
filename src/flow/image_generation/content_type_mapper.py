"""Content-type to image-design mapping.

Covers every content type in CONTENT_TYPE_TO_GENERATED_MODEL across all
four search intents. Every generated content type supports images via
BaseGeneratedContent.images and the generate_image agent tool.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.flow.image_generation.models import (
    AspectRatio,
    CameraAngle,
    ContentType,
    ImageGoal,
    ImageIntent,
    ImageOrientation,
    ImageType,
    LightingStyle,
    RenderingStyle,
    SearchIntent,
)


@dataclass(frozen=True)
class ContentTypeDesign:
    """Design system entry for a content type."""

    content_type: ContentType
    label: str
    image_type: ImageType
    rendering_style: RenderingStyle
    lighting: LightingStyle
    camera: CameraAngle
    image_goal: ImageGoal
    image_intent: ImageIntent
    aspect_ratio: AspectRatio
    orientation: ImageOrientation
    environment_hint: str
    story_template: str
    search_intent: SearchIntent = SearchIntent.INFORMATIONAL


def _d(
    content_type: ContentType,
    label: str,
    image_type: ImageType,
    rendering_style: RenderingStyle,
    lighting: LightingStyle,
    camera: CameraAngle,
    image_goal: ImageGoal,
    environment_hint: str,
    story_template: str,
    search_intent: SearchIntent,
    *,
    image_intent: ImageIntent = ImageIntent.FEATURED,
    aspect_ratio: AspectRatio = AspectRatio.LANDSCAPE,
    orientation: ImageOrientation = ImageOrientation.LANDSCAPE,
) -> ContentTypeDesign:
    return ContentTypeDesign(
        content_type=content_type,
        label=label,
        image_type=image_type,
        rendering_style=rendering_style,
        lighting=lighting,
        camera=camera,
        image_goal=image_goal,
        image_intent=image_intent,
        aspect_ratio=aspect_ratio,
        orientation=orientation,
        environment_hint=environment_hint,
        story_template=story_template,
        search_intent=search_intent,
    )


CONTENT_TYPE_DESIGNS: dict[ContentType, ContentTypeDesign] = {
    # ==================================================================
    # INFORMATIONAL (11 Rext + news design-system)
    # ==================================================================
    ContentType.BLOG: _d(
        ContentType.BLOG,
        "Editorial Hero Illustration",
        ImageType.EDITORIAL_HERO,
        RenderingStyle.EDITORIAL_ILLUSTRATION,
        LightingStyle.VOLUMETRIC,
        CameraAngle.WIDE,
        ImageGoal.ATTRACT_ATTENTION,
        "modern professional editorial environment",
        "a scene that visually introduces {topic} for {audience}, "
        "with the narrative centered on {subject}",
        SearchIntent.INFORMATIONAL,
    ),
    ContentType.TUTORIAL: _d(
        ContentType.TUTORIAL,
        "Workflow Illustration",
        ImageType.WORKFLOW,
        RenderingStyle.FLAT_ILLUSTRATION,
        LightingStyle.SOFT,
        CameraAngle.ISOMETRIC,
        ImageGoal.GUIDE_PROCESS,
        "clean instructional workspace with staged workflow",
        "a clear workflow scene showing how to approach {topic}, "
        "with {subject} as the guiding visual anchor",
        SearchIntent.INFORMATIONAL,
    ),
    ContentType.HOW_TO_GUIDE: _d(
        ContentType.HOW_TO_GUIDE,
        "Workflow Illustration",
        ImageType.WORKFLOW,
        RenderingStyle.FLAT_ILLUSTRATION,
        LightingStyle.SOFT,
        CameraAngle.ISOMETRIC,
        ImageGoal.GUIDE_PROCESS,
        "clean instructional workspace with staged workflow",
        "a clear how-to scene for {topic}, guiding the viewer "
        "through {subject} with calm instructional clarity",
        SearchIntent.INFORMATIONAL,
    ),
    ContentType.CHECKLIST: _d(
        ContentType.CHECKLIST,
        "Organized Process Illustration",
        ImageType.PROCESS,
        RenderingStyle.MINIMAL,
        LightingStyle.SOFT,
        CameraAngle.TOP_DOWN,
        ImageGoal.GUIDE_PROCESS,
        "organized process board with orderly stages",
        "an organized process scene for {topic}, presenting "
        "{subject} as a calm sequence of actionable steps",
        SearchIntent.INFORMATIONAL,
    ),
    ContentType.CASE_STUDY: _d(
        ContentType.CASE_STUDY,
        "Real Business Photography Style",
        ImageType.BUSINESS_PHOTO,
        RenderingStyle.PHOTOREALISTIC,
        LightingStyle.NATURAL,
        CameraAngle.EYE_LEVEL,
        ImageGoal.BUILD_TRUST,
        "authentic modern workplace or business setting",
        "a credible business scene representing a real-world outcome for "
        "{topic}, with {subject} grounded in authentic professional context",
        SearchIntent.INFORMATIONAL,
    ),
    ContentType.WHITEPAPER: _d(
        ContentType.WHITEPAPER,
        "Minimal Executive Illustration",
        ImageType.EXECUTIVE_MINIMAL,
        RenderingStyle.MINIMAL,
        LightingStyle.STUDIO,
        CameraAngle.WIDE,
        ImageGoal.SUPPORT_NARRATIVE,
        "minimal executive conceptual space",
        "a minimal executive scene that frames {topic} with "
        "quiet authority, using {subject} as a refined conceptual anchor",
        SearchIntent.INFORMATIONAL,
    ),
    ContentType.EXPLAINER: _d(
        ContentType.EXPLAINER,
        "Concept Illustration",
        ImageType.CONCEPT,
        RenderingStyle.EDITORIAL_ILLUSTRATION,
        LightingStyle.SOFT,
        CameraAngle.WIDE,
        ImageGoal.EXPLAIN_CONCEPT,
        "clear conceptual explanation space",
        "a clear concept illustration that demystifies {topic}, "
        "anchored by {subject} for immediate understanding",
        SearchIntent.INFORMATIONAL,
    ),
    ContentType.PILLAR_CONTENT: _d(
        ContentType.PILLAR_CONTENT,
        "Editorial Hero Illustration",
        ImageType.EDITORIAL_HERO,
        RenderingStyle.EDITORIAL_ILLUSTRATION,
        LightingStyle.VOLUMETRIC,
        CameraAngle.WIDE,
        ImageGoal.SUPPORT_NARRATIVE,
        "expansive authoritative editorial environment",
        "a wide editorial hero scene establishing {topic} as a definitive "
        "resource, with {subject} as the commanding focal idea",
        SearchIntent.INFORMATIONAL,
    ),
    ContentType.FAQ: _d(
        ContentType.FAQ,
        "Friendly Minimal Illustration",
        ImageType.FRIENDLY_MINIMAL,
        RenderingStyle.FLAT_ILLUSTRATION,
        LightingStyle.SOFT,
        CameraAngle.EYE_LEVEL,
        ImageGoal.EXPLAIN_CONCEPT,
        "friendly minimal help-center space",
        "a friendly minimal illustration that reassures readers about "
        "{topic}, with {subject} kept simple and approachable",
        SearchIntent.INFORMATIONAL,
        aspect_ratio=AspectRatio.SQUARE,
        orientation=ImageOrientation.SQUARE,
    ),
    ContentType.GLOSSARY: _d(
        ContentType.GLOSSARY,
        "Concept Illustration",
        ImageType.CONCEPT,
        RenderingStyle.ABSTRACT,
        LightingStyle.AMBIENT,
        CameraAngle.CLOSE_UP,
        ImageGoal.EXPLAIN_CONCEPT,
        "abstract conceptual field",
        "a focused concept illustration that defines {topic} visually, "
        "using {subject} as a memorable symbolic form",
        SearchIntent.INFORMATIONAL,
        aspect_ratio=AspectRatio.SQUARE,
        orientation=ImageOrientation.SQUARE,
    ),
    ContentType.RESOURCE_LIST: _d(
        ContentType.RESOURCE_LIST,
        "Resource Collection Illustration",
        ImageType.RESOURCE_COLLECTION,
        RenderingStyle.FLAT_ILLUSTRATION,
        LightingStyle.SOFT,
        CameraAngle.TOP_DOWN,
        ImageGoal.GUIDE_PROCESS,
        "organized library of curated resources",
        "an organized resource collection scene for {topic}, "
        "with {subject} presented as a curated set of valuable materials",
        SearchIntent.INFORMATIONAL,
    ),
    ContentType.NEWS: _d(
        ContentType.NEWS,
        "Editorial Photography Style",
        ImageType.EDITORIAL_PHOTO,
        RenderingStyle.PHOTOREALISTIC,
        LightingStyle.NATURAL,
        CameraAngle.EYE_LEVEL,
        ImageGoal.SUPPORT_NARRATIVE,
        "contemporary editorial reportage setting",
        "an editorial photography-style scene covering {topic}, "
        "with {subject} presented with journalistic credibility",
        SearchIntent.INFORMATIONAL,
    ),
    # ==================================================================
    # COMMERCIAL
    # ==================================================================
    ContentType.COMPARISON: _d(
        ContentType.COMPARISON,
        "Split Layout",
        ImageType.SPLIT_LAYOUT,
        RenderingStyle.FLAT_ILLUSTRATION,
        LightingStyle.SOFT,
        CameraAngle.EYE_LEVEL,
        ImageGoal.EXPLAIN_CONCEPT,
        "clean split comparative layout",
        "a balanced split-layout visual comparing sides of {topic}, "
        "keeping {subject} clear and evenly weighted",
        SearchIntent.COMMERCIAL,
    ),
    ContentType.BEST_TOOLS: _d(
        ContentType.BEST_TOOLS,
        "Product Grid Illustration",
        ImageType.PRODUCT_GRID,
        RenderingStyle.FLAT_ILLUSTRATION,
        LightingStyle.SOFT,
        CameraAngle.TOP_DOWN,
        ImageGoal.SHOWCASE_PRODUCT,
        "organized showcase of top tools and platforms",
        "a curated product-grid scene for {topic}, "
        "with {subject} highlighted among carefully ranked options",
        SearchIntent.COMMERCIAL,
    ),
    ContentType.ALTERNATIVES: _d(
        ContentType.ALTERNATIVES,
        "Comparison Roundup Illustration",
        ImageType.COMPARISON_ROUNDUP,
        RenderingStyle.FLAT_ILLUSTRATION,
        LightingStyle.SOFT,
        CameraAngle.WIDE,
        ImageGoal.EXPLAIN_CONCEPT,
        "clean alternative-options landscape",
        "a clear alternatives landscape for {topic}, "
        "positioning {subject} among viable competing choices",
        SearchIntent.COMMERCIAL,
    ),
    ContentType.PRODUCT_REVIEW: _d(
        ContentType.PRODUCT_REVIEW,
        "Product Showcase",
        ImageType.PRODUCT_SHOWCASE,
        RenderingStyle.PRODUCT_SHOWCASE,
        LightingStyle.STUDIO,
        CameraAngle.CLOSE_UP,
        ImageGoal.SHOWCASE_PRODUCT,
        "clean product studio showcase",
        "a premium product showcase for {topic}, presenting {subject} "
        "with studio clarity and persuasive detail",
        SearchIntent.COMMERCIAL,
        aspect_ratio=AspectRatio.SQUARE,
        orientation=ImageOrientation.SQUARE,
    ),
    ContentType.PROS_CONS: _d(
        ContentType.PROS_CONS,
        "Split Layout",
        ImageType.SPLIT_LAYOUT,
        RenderingStyle.MINIMAL,
        LightingStyle.SOFT,
        CameraAngle.EYE_LEVEL,
        ImageGoal.EXPLAIN_CONCEPT,
        "balanced pros-and-cons conceptual layout",
        "a balanced split visual weighing strengths and weaknesses of "
        "{topic}, with {subject} as the evaluated focal idea",
        SearchIntent.COMMERCIAL,
    ),
    ContentType.PRODUCT_ROUNDUP: _d(
        ContentType.PRODUCT_ROUNDUP,
        "Product Grid Illustration",
        ImageType.PRODUCT_GRID,
        RenderingStyle.FLAT_ILLUSTRATION,
        LightingStyle.SOFT,
        CameraAngle.WIDE,
        ImageGoal.SHOWCASE_PRODUCT,
        "editorial product roundup showcase",
        "an editorial roundup scene for {topic}, "
        "arranging {subject} among featured products in a clean grid",
        SearchIntent.COMMERCIAL,
    ),
    ContentType.BUYING_GUIDE: _d(
        ContentType.BUYING_GUIDE,
        "Organized Process Illustration",
        ImageType.PROCESS,
        RenderingStyle.EDITORIAL_ILLUSTRATION,
        LightingStyle.SOFT,
        CameraAngle.WIDE,
        ImageGoal.GUIDE_PROCESS,
        "guided decision-making environment",
        "a buying-guide scene that helps {audience} evaluate {topic}, "
        "with {subject} as the decision-framework visual anchor",
        SearchIntent.COMMERCIAL,
    ),
    # ==================================================================
    # NAVIGATIONAL
    # ==================================================================
    ContentType.BRAND_PAGE: _d(
        ContentType.BRAND_PAGE,
        "Brand Identity Illustration",
        ImageType.BRAND_IDENTITY,
        RenderingStyle.EDITORIAL_ILLUSTRATION,
        LightingStyle.STUDIO,
        CameraAngle.WIDE,
        ImageGoal.BUILD_TRUST,
        "polished brand identity environment",
        "a brand-identity scene for {topic}, presenting {subject} "
        "with confident corporate presence and trust",
        SearchIntent.NAVIGATIONAL,
    ),
    ContentType.PRODUCT_HOMEPAGE: _d(
        ContentType.PRODUCT_HOMEPAGE,
        "Hero Marketing Illustration",
        ImageType.HERO_MARKETING,
        RenderingStyle.THREE_D_RENDER,
        LightingStyle.VOLUMETRIC,
        CameraAngle.WIDE,
        ImageGoal.SHOWCASE_PRODUCT,
        "premium product homepage hero environment",
        "a product-homepage hero scene for {topic}, "
        "spotlighting {subject} as the flagship visual centerpiece",
        SearchIntent.NAVIGATIONAL,
        image_intent=ImageIntent.HERO,
    ),
    ContentType.FEATURE_OVERVIEW: _d(
        ContentType.FEATURE_OVERVIEW,
        "Feature Highlight Illustration",
        ImageType.FEATURE_HIGHLIGHT,
        RenderingStyle.THREE_D_RENDER,
        LightingStyle.SOFT,
        CameraAngle.ISOMETRIC,
        ImageGoal.EXPLAIN_CONCEPT,
        "clean feature-highlight product space",
        "a feature-overview scene for {topic}, "
        "with {subject} illuminated as the key capability to understand",
        SearchIntent.NAVIGATIONAL,
    ),
    ContentType.DOCUMENTATION: _d(
        ContentType.DOCUMENTATION,
        "Technical Illustration",
        ImageType.TECHNICAL,
        RenderingStyle.BLUEPRINT,
        LightingStyle.STUDIO,
        CameraAngle.ISOMETRIC,
        ImageGoal.EXPLAIN_CONCEPT,
        "precise technical diagram space",
        "a precise technical illustration explaining {topic}, "
        "with {subject} rendered for clarity and structure",
        SearchIntent.NAVIGATIONAL,
        image_intent=ImageIntent.INLINE,
        aspect_ratio=AspectRatio.STANDARD,
    ),
    ContentType.LOGIN_GUIDE: _d(
        ContentType.LOGIN_GUIDE,
        "Workflow Illustration",
        ImageType.WORKFLOW,
        RenderingStyle.FLAT_ILLUSTRATION,
        LightingStyle.SOFT,
        CameraAngle.EYE_LEVEL,
        ImageGoal.GUIDE_PROCESS,
        "simple secure access workflow space",
        "a calm login-guide scene for {topic}, "
        "showing {subject} as a clear secure access pathway",
        SearchIntent.NAVIGATIONAL,
    ),
    ContentType.CONTACT_US: _d(
        ContentType.CONTACT_US,
        "Friendly Minimal Illustration",
        ImageType.FRIENDLY_MINIMAL,
        RenderingStyle.FLAT_ILLUSTRATION,
        LightingStyle.SOFT,
        CameraAngle.EYE_LEVEL,
        ImageGoal.BUILD_TRUST,
        "approachable contact and support environment",
        "a friendly contact scene for {topic}, "
        "with {subject} communicating openness and easy reachability",
        SearchIntent.NAVIGATIONAL,
    ),
    ContentType.ABOUT_US: _d(
        ContentType.ABOUT_US,
        "Human Centric Illustration",
        ImageType.HUMAN_CENTRIC,
        RenderingStyle.EDITORIAL_ILLUSTRATION,
        LightingStyle.NATURAL,
        CameraAngle.EYE_LEVEL,
        ImageGoal.BUILD_TRUST,
        "human-centric brand environment",
        "a human-centric brand scene for {topic}, highlighting people "
        "connected to {subject} with warmth and authenticity",
        SearchIntent.NAVIGATIONAL,
    ),
    ContentType.HELP_CENTER: _d(
        ContentType.HELP_CENTER,
        "Friendly Minimal Illustration",
        ImageType.FRIENDLY_MINIMAL,
        RenderingStyle.FLAT_ILLUSTRATION,
        LightingStyle.SOFT,
        CameraAngle.EYE_LEVEL,
        ImageGoal.EXPLAIN_CONCEPT,
        "friendly help-center support environment",
        "a reassuring help-center scene for {topic}, "
        "with {subject} presented as clear guided assistance",
        SearchIntent.NAVIGATIONAL,
    ),
    # ==================================================================
    # TRANSACTIONAL
    # ==================================================================
    ContentType.LANDING_PAGE: _d(
        ContentType.LANDING_PAGE,
        "Hero Marketing Illustration",
        ImageType.HERO_MARKETING,
        RenderingStyle.THREE_D_RENDER,
        LightingStyle.DRAMATIC,
        CameraAngle.WIDE,
        ImageGoal.DRIVE_CONVERSION,
        "bold marketing hero environment with product presence",
        "a bold hero marketing scene for {topic}, spotlighting {subject} "
        "as the conversion-focused visual centerpiece",
        SearchIntent.TRANSACTIONAL,
        image_intent=ImageIntent.HERO,
    ),
    ContentType.SALES_PAGE: _d(
        ContentType.SALES_PAGE,
        "Conversion Hero Illustration",
        ImageType.CONVERSION_HERO,
        RenderingStyle.CINEMATIC,
        LightingStyle.DRAMATIC,
        CameraAngle.WIDE,
        ImageGoal.DRIVE_CONVERSION,
        "persuasive sales hero environment",
        "a persuasive sales-page scene for {topic}, "
        "with {subject} framed to create desire and urgency",
        SearchIntent.TRANSACTIONAL,
        image_intent=ImageIntent.HERO,
    ),
    ContentType.PRICING_PAGE: _d(
        ContentType.PRICING_PAGE,
        "Pricing Visual Illustration",
        ImageType.PRICING_VISUAL,
        RenderingStyle.MINIMAL,
        LightingStyle.STUDIO,
        CameraAngle.EYE_LEVEL,
        ImageGoal.DRIVE_CONVERSION,
        "clean transparent pricing presentation space",
        "a clean pricing visual for {topic}, "
        "presenting {subject} with clarity, value, and confidence",
        SearchIntent.TRANSACTIONAL,
    ),
    ContentType.SIGNUP_PAGE: _d(
        ContentType.SIGNUP_PAGE,
        "Conversion Hero Illustration",
        ImageType.CONVERSION_HERO,
        RenderingStyle.FLAT_ILLUSTRATION,
        LightingStyle.SOFT,
        CameraAngle.EYE_LEVEL,
        ImageGoal.DRIVE_CONVERSION,
        "welcoming signup onboarding environment",
        "a welcoming signup scene for {topic}, "
        "with {subject} inviting a confident first step",
        SearchIntent.TRANSACTIONAL,
    ),
    ContentType.DEMO_PAGE: _d(
        ContentType.DEMO_PAGE,
        "Product Showcase",
        ImageType.PRODUCT_SHOWCASE,
        RenderingStyle.THREE_D_RENDER,
        LightingStyle.VOLUMETRIC,
        CameraAngle.WIDE,
        ImageGoal.SHOWCASE_PRODUCT,
        "interactive product demo environment",
        "a product-demo scene for {topic}, "
        "showcasing {subject} in action with clear experiential appeal",
        SearchIntent.TRANSACTIONAL,
        image_intent=ImageIntent.HERO,
    ),
    ContentType.COUPON_PAGE: _d(
        ContentType.COUPON_PAGE,
        "Conversion Hero Illustration",
        ImageType.CONVERSION_HERO,
        RenderingStyle.FLAT_ILLUSTRATION,
        LightingStyle.SOFT,
        CameraAngle.EYE_LEVEL,
        ImageGoal.DRIVE_CONVERSION,
        "promotional offer environment without readable coupon text",
        "a promotional offer scene for {topic}, "
        "with {subject} communicating value and timely opportunity",
        SearchIntent.TRANSACTIONAL,
    ),
    ContentType.CHECKOUT_PAGE: _d(
        ContentType.CHECKOUT_PAGE,
        "Minimal Executive Illustration",
        ImageType.EXECUTIVE_MINIMAL,
        RenderingStyle.MINIMAL,
        LightingStyle.STUDIO,
        CameraAngle.EYE_LEVEL,
        ImageGoal.BUILD_TRUST,
        "secure calm checkout confidence environment",
        "a calm secure checkout scene for {topic}, "
        "with {subject} communicating trust and frictionless completion",
        SearchIntent.TRANSACTIONAL,
    ),
    ContentType.SERVICE_PAGE: _d(
        ContentType.SERVICE_PAGE,
        "Hero Marketing Illustration",
        ImageType.HERO_MARKETING,
        RenderingStyle.EDITORIAL_ILLUSTRATION,
        LightingStyle.NATURAL,
        CameraAngle.WIDE,
        ImageGoal.DRIVE_CONVERSION,
        "professional service delivery environment",
        "a professional service-page scene for {topic}, "
        "presenting {subject} as a trusted high-value offering",
        SearchIntent.TRANSACTIONAL,
        image_intent=ImageIntent.HERO,
    ),
}


# Map every Rext canonical key (kebab-case) + common variants → ContentType
CONTENT_TYPE_ALIASES: dict[str, ContentType] = {
    # Informational
    "blog": ContentType.BLOG,
    "blog_post": ContentType.BLOG,
    "blog-post": ContentType.BLOG,
    "article": ContentType.BLOG,
    "post": ContentType.BLOG,
    "listicle": ContentType.BLOG,
    "tutorial": ContentType.TUTORIAL,
    "how_to": ContentType.HOW_TO_GUIDE,
    "how-to": ContentType.HOW_TO_GUIDE,
    "how_to_guide": ContentType.HOW_TO_GUIDE,
    "how-to-guide": ContentType.HOW_TO_GUIDE,
    "checklist": ContentType.CHECKLIST,
    "case_study": ContentType.CASE_STUDY,
    "case-study": ContentType.CASE_STUDY,
    "whitepaper": ContentType.WHITEPAPER,
    "white_paper": ContentType.WHITEPAPER,
    "white-paper": ContentType.WHITEPAPER,
    "explainer": ContentType.EXPLAINER,
    "pillar": ContentType.PILLAR_CONTENT,
    "pillar_content": ContentType.PILLAR_CONTENT,
    "pillar-content": ContentType.PILLAR_CONTENT,
    "faq": ContentType.FAQ,
    "glossary": ContentType.GLOSSARY,
    "resource_list": ContentType.RESOURCE_LIST,
    "resource-list": ContentType.RESOURCE_LIST,
    "news": ContentType.NEWS,
    # Commercial
    "comparison": ContentType.COMPARISON,
    "vs": ContentType.COMPARISON,
    "best_tools": ContentType.BEST_TOOLS,
    "best-tools": ContentType.BEST_TOOLS,
    "alternatives": ContentType.ALTERNATIVES,
    "product_review": ContentType.PRODUCT_REVIEW,
    "product-review": ContentType.PRODUCT_REVIEW,
    "review": ContentType.PRODUCT_REVIEW,
    "in_depth_review": ContentType.PRODUCT_REVIEW,
    "in-depth-review": ContentType.PRODUCT_REVIEW,
    "pros_cons": ContentType.PROS_CONS,
    "pros-cons": ContentType.PROS_CONS,
    "product_roundup": ContentType.PRODUCT_ROUNDUP,
    "product-roundup": ContentType.PRODUCT_ROUNDUP,
    "buying_guide": ContentType.BUYING_GUIDE,
    "buying-guide": ContentType.BUYING_GUIDE,
    # Navigational
    "brand_page": ContentType.BRAND_PAGE,
    "brand-page": ContentType.BRAND_PAGE,
    "product_homepage": ContentType.PRODUCT_HOMEPAGE,
    "product-homepage": ContentType.PRODUCT_HOMEPAGE,
    "feature_overview": ContentType.FEATURE_OVERVIEW,
    "feature-overview": ContentType.FEATURE_OVERVIEW,
    "documentation": ContentType.DOCUMENTATION,
    "docs": ContentType.DOCUMENTATION,
    "login_guide": ContentType.LOGIN_GUIDE,
    "login-guide": ContentType.LOGIN_GUIDE,
    "contact_us": ContentType.CONTACT_US,
    "contact-us": ContentType.CONTACT_US,
    "about_us": ContentType.ABOUT_US,
    "about-us": ContentType.ABOUT_US,
    "help_center": ContentType.HELP_CENTER,
    "help-center": ContentType.HELP_CENTER,
    # Transactional
    "landing_page": ContentType.LANDING_PAGE,
    "landing-page": ContentType.LANDING_PAGE,
    "sales_page": ContentType.SALES_PAGE,
    "sales-page": ContentType.SALES_PAGE,
    "pricing_page": ContentType.PRICING_PAGE,
    "pricing-page": ContentType.PRICING_PAGE,
    "signup_page": ContentType.SIGNUP_PAGE,
    "signup-page": ContentType.SIGNUP_PAGE,
    "demo_page": ContentType.DEMO_PAGE,
    "demo-page": ContentType.DEMO_PAGE,
    "coupon_page": ContentType.COUPON_PAGE,
    "coupon-page": ContentType.COUPON_PAGE,
    "checkout_page": ContentType.CHECKOUT_PAGE,
    "checkout-page": ContentType.CHECKOUT_PAGE,
    "service_page": ContentType.SERVICE_PAGE,
    "service-page": ContentType.SERVICE_PAGE,
}


# Every Rext generated content type (must stay in sync with contents/__init__.py)
REXT_CONTENT_TYPES_BY_INTENT: dict[SearchIntent, tuple[str, ...]] = {
    SearchIntent.INFORMATIONAL: (
        "blog",
        "how-to-guide",
        "explainer",
        "pillar-content",
        "checklist",
        "tutorial",
        "faq",
        "white-paper",
        "case-study",
        "glossary",
        "resource-list",
    ),
    SearchIntent.COMMERCIAL: (
        "comparison",
        "best-tools",
        "alternatives",
        "in-depth-review",
        "pros-cons",
        "product-roundup",
        "buying-guide",
    ),
    SearchIntent.NAVIGATIONAL: (
        "brand-page",
        "product-homepage",
        "feature-overview",
        "documentation",
        "login-guide",
        "contact-us",
        "about-us",
        "help-center",
    ),
    SearchIntent.TRANSACTIONAL: (
        "sales-page",
        "pricing-page",
        "signup-page",
        "demo-page",
        "coupon-page",
        "checkout-page",
        "landing-page",
        "service-page",
    ),
}


INTENT_GOAL_OVERRIDES: dict[SearchIntent, ImageGoal] = {
    SearchIntent.INFORMATIONAL: ImageGoal.EXPLAIN_CONCEPT,
    SearchIntent.COMMERCIAL: ImageGoal.SHOWCASE_PRODUCT,
    SearchIntent.NAVIGATIONAL: ImageGoal.BUILD_TRUST,
    SearchIntent.TRANSACTIONAL: ImageGoal.DRIVE_CONVERSION,
}


def normalize_content_type(value: str | ContentType | None) -> ContentType:
    """Normalize freeform / kebab-case / snake_case content type strings."""
    if isinstance(value, ContentType):
        return value
    if not value:
        return ContentType.BLOG

    raw = value.strip().lower()
    # Accept both kebab-case (Rext canonical) and snake_case
    key = raw.replace(" ", "-").replace("_", "-")
    snake = key.replace("-", "_")

    if key in CONTENT_TYPE_ALIASES:
        return CONTENT_TYPE_ALIASES[key]
    if snake in CONTENT_TYPE_ALIASES:
        return CONTENT_TYPE_ALIASES[snake]
    if raw in CONTENT_TYPE_ALIASES:
        return CONTENT_TYPE_ALIASES[raw]

    try:
        return ContentType(snake)
    except ValueError:
        return ContentType.BLOG


def get_content_type_design(content_type: ContentType | str) -> ContentTypeDesign:
    """Return the design system entry for a content type."""
    normalized = normalize_content_type(content_type)
    return CONTENT_TYPE_DESIGNS.get(normalized, CONTENT_TYPE_DESIGNS[ContentType.BLOG])


def all_rext_content_types_supported() -> bool:
    """True when every Rext content type has a dedicated design mapping."""
    for keys in REXT_CONTENT_TYPES_BY_INTENT.values():
        for key in keys:
            design = get_content_type_design(key)
            # Must not silently fall back unless the key IS blog
            if key != "blog" and design.content_type == ContentType.BLOG:
                # Fallback detection: alias resolved to blog incorrectly
                if normalize_content_type(key) == ContentType.BLOG:
                    return False
            if design.content_type not in CONTENT_TYPE_DESIGNS:
                return False
    return True
