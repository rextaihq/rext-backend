from .infomational import (
    BlogOutline,
    HowToGuideOutline,
    ExplainerOutline,
    PillarContentOutline,
    ChecklistOutline,
    TutorialOutline,
    FAQOutline,
    WhitePaperOutline,
    CaseStudyOutline,
    GlossaryOutline,
    ResourceListOutline,
)

from .commercial import (
    ComparisonOutline,
    BestToolsOutline,
    AlternativesOutline,
    InDepthReviewOutline,
    ProsConsOutline,
    ProductRoundupOutline,
    BuyingGuideOutline,
)

from .navigational import (
    BrandPageOutline,
    ProductHomepageOutline,
    FeatureOverviewOutline,
    DocumentationOutline,
    LoginGuideOutline,
    ContactUsOutline,
    AboutUsOutline,
    HelpCenterOutline,
)

from .transactional import (
    SalesPageOutline,
    PricingPageOutline,
    SignupPageOutline,
    DemoPageOutline,
    CouponPageOutline,
    CheckoutPageOutline,
    LandingPageOutline,
    ServicePageOutline,
)

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
    return CONTENT_TYPE_TO_MODEL.get(content_type, BlogOutline)


def get_outline_display_name(content_type: str) -> str:
    """Convert a content type key to a human-readable display name.

    e.g. 'brand-page' -> 'Brand Page', 'how-to-guide' -> 'How To Guide'
    """
    return content_type.replace("-", " ").title()

__all__ = [
    "get_outline_model",
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
