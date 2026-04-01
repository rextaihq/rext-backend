from .infomational import (
    BlogGeneratedContent,
    HowToGuideGeneratedContent,
    ExplainerGeneratedContent,
    PillarContentGeneratedContent,
    ChecklistGeneratedContent,
    TutorialGeneratedContent,
    FAQGeneratedContent,
    WhitePaperGeneratedContent,
    CaseStudyGeneratedContent,
    GlossaryGeneratedContent,
    ResourceListGeneratedContent,
)

from .commercial import (
    ComparisonGeneratedContent,
    BestToolsGeneratedContent,
    AlternativesGeneratedContent,
    InDepthReviewGeneratedContent,
    ProsConsGeneratedContent,
    ProductRoundupGeneratedContent,
    BuyingGuideGeneratedContent,
)

from .navigational import (
    BrandPageGeneratedContent,
    ProductHomepageGeneratedContent,
    FeatureOverviewGeneratedContent,
    DocumentationGeneratedContent,
    LoginGuideGeneratedContent,
    ContactUsGeneratedContent,
    AboutUsGeneratedContent,
    HelpCenterGeneratedContent,
)

from .transactional import (
    SalesPageGeneratedContent,
    PricingPageGeneratedContent,
    SignupPageGeneratedContent,
    DemoPageGeneratedContent,
    CouponPageGeneratedContent,
    CheckoutPageGeneratedContent,
    LandingPageGeneratedContent,
    ServicePageGeneratedContent,
)

CONTENT_TYPE_TO_GENERATED_MODEL = {
    # Informational
    "blog": BlogGeneratedContent,
    "how-to-guide": HowToGuideGeneratedContent,
    "explainer": ExplainerGeneratedContent,
    "pillar-content": PillarContentGeneratedContent,
    "checklist": ChecklistGeneratedContent,
    "tutorial": TutorialGeneratedContent,
    "faq": FAQGeneratedContent,
    "white-paper": WhitePaperGeneratedContent,
    "case-study": CaseStudyGeneratedContent,
    "glossary": GlossaryGeneratedContent,
    "resource-list": ResourceListGeneratedContent,

    # Commercial 
    "comparison": ComparisonGeneratedContent,
    "best-tools": BestToolsGeneratedContent,
    "alternatives": AlternativesGeneratedContent,
    "in-depth-review": InDepthReviewGeneratedContent,
    "pros-cons": ProsConsGeneratedContent,
    "product-roundup": ProductRoundupGeneratedContent,
    "buying-guide": BuyingGuideGeneratedContent,
    
    # Navigational
    "brand-page": BrandPageGeneratedContent,
    "product-homepage": ProductHomepageGeneratedContent,
    "feature-overview": FeatureOverviewGeneratedContent,
    "documentation": DocumentationGeneratedContent,
    "login-guide": LoginGuideGeneratedContent,
    "contact-us": ContactUsGeneratedContent,
    "about-us": AboutUsGeneratedContent,
    "help-center": HelpCenterGeneratedContent,
    
    # Transactional
    "sales-page": SalesPageGeneratedContent,
    "pricing-page": PricingPageGeneratedContent,
    "signup-page": SignupPageGeneratedContent,
    "demo-page": DemoPageGeneratedContent,
    "coupon-page": CouponPageGeneratedContent,
    "checkout-page": CheckoutPageGeneratedContent,
    "landing-page": LandingPageGeneratedContent,
    "service-page": ServicePageGeneratedContent,
}

def get_generated_content_model(content_type: str):
    """Get the appropriate Pydantic model for a given content type."""
    return CONTENT_TYPE_TO_GENERATED_MODEL.get(content_type, BlogGeneratedContent)

__all__ = [
    "get_generated_content_model",
    "CONTENT_TYPE_TO_GENERATED_MODEL",
    
    # Informational
    "BlogGeneratedContent",
    "HowToGuideGeneratedContent",
    "ExplainerGeneratedContent",
    "PillarContentGeneratedContent",
    "ChecklistGeneratedContent",
    "TutorialGeneratedContent",
    "FAQGeneratedContent",
    "WhitePaperGeneratedContent",
    "CaseStudyGeneratedContent",
    "GlossaryGeneratedContent",
    "ResourceListGeneratedContent",
    
    # Commercial
    "ComparisonGeneratedContent",
    "BestToolsGeneratedContent",
    "AlternativesGeneratedContent",
    "InDepthReviewGeneratedContent",
    "ProsConsGeneratedContent",
    "ProductRoundupGeneratedContent",
    "BuyingGuideGeneratedContent",
    
    # Navigational
    "BrandPageGeneratedContent",
    "ProductHomepageGeneratedContent",
    "FeatureOverviewGeneratedContent",
    "DocumentationGeneratedContent",
    "LoginGuideGeneratedContent",
    "ContactUsGeneratedContent",
    "AboutUsGeneratedContent",
    "HelpCenterGeneratedContent",
    
    # Transactional
    "SalesPageGeneratedContent",
    "PricingPageGeneratedContent",
    "SignupPageGeneratedContent",
    "DemoPageGeneratedContent",
    "CouponPageGeneratedContent",
    "CheckoutPageGeneratedContent",
    "LandingPageGeneratedContent",
    "ServicePageGeneratedContent",
]
