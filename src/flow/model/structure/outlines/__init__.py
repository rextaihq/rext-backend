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


# The length the gate accepts for a content type whose model doesn't bound its own.
_DEFAULT_WORD_COUNT_RANGE = (100, 15000)

# The longest article the writer can return. It writes the whole article in one response of
# at most CONTENT_GENERATION_MAX_TOKENS (llm_manager.py, 16,384): about two output tokens a
# word once the markup, the length band's upper edge and the response's other fields are
# counted. A longer target would be cut off mid-article, so the gate brings it down to this.
WRITER_MAX_TARGET_WORDS = 8000


# The most the product shows for a type, where that is less than its outline model allows. A
# blog is 800 to 2,000 words on the content-type step and beside the outline's Target words;
# its model inherits the base bound (5,000). Held here and not on the model: structured output
# is not strict, and a run whose model wrote a larger target would fail on a tighter bound.
# By model, so a type nobody knows, which is given the blog's model, is held as a blog.
_SHOWN_MAX_WORDS: dict[type, int] = {BlogOutline: 2000}


def plan_ceiling(content_type: str) -> int | None:
    """The most a type's plan may add up to when the product's range is narrower than its
    outline model's own bound; None for a type whose model already declares its range."""
    return _SHOWN_MAX_WORDS.get(get_outline_model(content_type))


def target_word_count_range(content_type: str) -> tuple[int, int]:
    """The article length a content type accepts: the bounds its outline model declares on
    `target_word_count`, and no more than the product shows for the type. The dashboard offers
    the same range per type, so a length the screen allowed (a 300-word pricing page, a
    12,000-word white paper) is one the gate keeps, and one it refused is not let in here."""
    low, high = _DEFAULT_WORD_COUNT_RANGE
    field = get_outline_model(content_type).model_fields.get("target_word_count")
    for constraint in getattr(field, "metadata", None) or []:
        low = getattr(constraint, "ge", None) or low
        high = getattr(constraint, "le", None) or high
    return low, min(high, plan_ceiling(content_type) or high)


def get_outline_display_name(content_type: str) -> str:
    """Convert a content type key to a human-readable display name.

    e.g. 'brand-page' -> 'Brand Page', 'how-to-guide' -> 'How To Guide'
    """
    normalized = normalize_content_type(content_type) or (content_type or "")
    return str(normalized).replace("-", " ").title()


__all__ = [
    "get_outline_model",
    "target_word_count_range",
    "plan_ceiling",
    "WRITER_MAX_TARGET_WORDS",
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
