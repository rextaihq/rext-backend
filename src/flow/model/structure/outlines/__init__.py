from .commercial import (
    AlternativesOutline,
    BestToolsOutline,
    BuyingGuideOutline,
    ComparisonOutline,
    InDepthReviewOutline,
    ProductRoundupOutline,
    ProsConsOutline,
)
from .infomational import (
    BlogOutline,
    CaseStudyOutline,
    ChecklistOutline,
    ExplainerOutline,
    FAQOutline,
    GlossaryOutline,
    HowToGuideOutline,
    PillarContentOutline,
    ResourceListOutline,
    TutorialOutline,
    WhitePaperOutline,
)
from .navigational import (
    AboutUsOutline,
    BrandPageOutline,
    ContactUsOutline,
    DocumentationOutline,
    FeatureOverviewOutline,
    HelpCenterOutline,
    LoginGuideOutline,
    ProductHomepageOutline,
)
from .transactional import (
    CheckoutPageOutline,
    CouponPageOutline,
    DemoPageOutline,
    LandingPageOutline,
    PricingPageOutline,
    SalesPageOutline,
    ServicePageOutline,
    SignupPageOutline,
)


def normalize_content_type(content_type: str | None) -> str:
    """Normalize user/UI/legacy content-type values to canonical keys.

    Canonical keys are lower-kebab-case values used by the outline model maps,
    e.g. "landing-page", "how-to-guide".

    Examples:
      - "Landing Page" -> "landing-page"
      - "landing_page" -> "landing-page"
      - "ARTICLE" -> "blog" (alias)
    """
    if not content_type:
        return ""

    normalized = str(content_type).strip().lower()
    if not normalized:
        return ""

    normalized = normalized.replace("_", "-").replace(" ", "-")
    while "--" in normalized:
        normalized = normalized.replace("--", "-")
    normalized = normalized.strip("-")

    # Aliases used in the flow / legacy state
    if normalized in {"article", "post", "blog-post", "blogpost", "listicle"}:
        return "blog"

    return normalized


CONTENT_TYPE_TO_MODEL = {
    # Informational
    "blog": BlogOutline,
    "how-to-guide": HowToGuideOutline,
    "explainer": ExplainerOutline,
    "pillar-content": PillarContentOutline,
    "checklist": ChecklistOutline,
    "tutorial": TutorialOutline,
    "faq": FAQOutline,
    "white-paper": WhitePaperOutline,
    "case-study": CaseStudyOutline,
    "glossary": GlossaryOutline,
    "resource-list": ResourceListOutline,
    # Commercial
    "comparison": ComparisonOutline,
    "best-tools": BestToolsOutline,
    "alternatives": AlternativesOutline,
    "in-depth-review": InDepthReviewOutline,
    "pros-cons": ProsConsOutline,
    "product-roundup": ProductRoundupOutline,
    "buying-guide": BuyingGuideOutline,
    # Navigational
    "brand-page": BrandPageOutline,
    "product-homepage": ProductHomepageOutline,
    "feature-overview": FeatureOverviewOutline,
    "documentation": DocumentationOutline,
    "login-guide": LoginGuideOutline,
    "contact-us": ContactUsOutline,
    "about-us": AboutUsOutline,
    "help-center": HelpCenterOutline,
    # Transactional
    "sales-page": SalesPageOutline,
    "pricing-page": PricingPageOutline,
    "signup-page": SignupPageOutline,
    "demo-page": DemoPageOutline,
    "coupon-page": CouponPageOutline,
    "checkout-page": CheckoutPageOutline,
    "landing-page": LandingPageOutline,
    "service-page": ServicePageOutline,
}


def get_outline_model(content_type: str):
    """Get the appropriate Pydantic model for a given content type."""
    normalized = normalize_content_type(content_type)
    return CONTENT_TYPE_TO_MODEL.get(normalized, BlogOutline)


def get_outline_display_name(content_type: str) -> str:
    """Convert a content type key to a human-readable display name.

    e.g. 'brand-page' -> 'Brand Page', 'how-to-guide' -> 'How To Guide'
    """
    normalized = normalize_content_type(content_type) or (content_type or "")
    return str(normalized).replace("-", " ").title()


__all__ = [
    "get_outline_model",
    "normalize_content_type",
    "CONTENT_TYPE_TO_MODEL",
    # Informational
    "BlogOutline",
    "HowToGuideOutline",
    "ExplainerOutline",
    "PillarContentOutline",
    "ChecklistOutline",
    "TutorialOutline",
    "FAQOutline",
    "WhitePaperOutline",
    "CaseStudyOutline",
    "GlossaryOutline",
    "ResourceListOutline",
    # Commercial
    "ComparisonOutline",
    "BestToolsOutline",
    "AlternativesOutline",
    "InDepthReviewOutline",
    "ProsConsOutline",
    "ProductRoundupOutline",
    "BuyingGuideOutline",
    # Navigational
    "BrandPageOutline",
    "ProductHomepageOutline",
    "FeatureOverviewOutline",
    "DocumentationOutline",
    "LoginGuideOutline",
    "ContactUsOutline",
    "AboutUsOutline",
    "HelpCenterOutline",
    # Transactional
    "SalesPageOutline",
    "PricingPageOutline",
    "SignupPageOutline",
    "DemoPageOutline",
    "CouponPageOutline",
    "CheckoutPageOutline",
    "LandingPageOutline",
    "ServicePageOutline",
]
