from typing import Union
from .informational import (
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
    ComparisonOutlineState,
    BestToolsOutlineState,
    AlternativesOutlineState,
    InDepthReviewOutlineState,
    ProsConsOutlineState,
    ProductRoundupOutlineState,
    BuyingGuideOutlineState,
)

from .navigational import (
    BrandPageOutlineState,
    ProductHomepageOutlineState,
    FeatureOverviewOutlineState,
    DocumentationOutlineState,
    LoginGuideOutlineState,
    ContactUsOutlineState,
    AboutUsOutlineState,
    HelpCenterOutlineState,
)

from .transactional import (
    SalesPageOutlineState,
    PricingPageOutlineState,
    SignupPageOutlineState,
    DemoPageOutlineState,
    CouponPageOutlineState,
    CheckoutPageOutlineState,
    LandingPageOutlineState,
    ServicePageOutlineState,
)


OutlineState = Union[
    # Informational
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
    
    # Commercial
    ComparisonOutlineState,
    BestToolsOutlineState,
    AlternativesOutlineState,
    InDepthReviewOutlineState,
    ProsConsOutlineState,
    ProductRoundupOutlineState,
    BuyingGuideOutlineState,
    
    # Navigational
    BrandPageOutlineState,
    ProductHomepageOutlineState,
    FeatureOverviewOutlineState,
    DocumentationOutlineState,
    LoginGuideOutlineState,
    ContactUsOutlineState,
    AboutUsOutlineState,
    HelpCenterOutlineState,
    
    # Transactional
    SalesPageOutlineState,
    PricingPageOutlineState,
    SignupPageOutlineState,
    DemoPageOutlineState,
    CouponPageOutlineState,
    CheckoutPageOutlineState,
    LandingPageOutlineState,
    ServicePageOutlineState,
]

__all__ = [
    "OutlineState",
    
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
    "ComparisonOutlineState",
    "BestToolsOutlineState",
    "AlternativesOutlineState",
    "InDepthReviewOutlineState",
    "ProsConsOutlineState",
    "ProductRoundupOutlineState",
    "BuyingGuideOutlineState",
    
    # Navigational
    "BrandPageOutlineState",
    "ProductHomepageOutlineState",
    "FeatureOverviewOutlineState",
    "DocumentationOutlineState",
    "LoginGuideOutlineState",
    "ContactUsOutlineState",
    "AboutUsOutlineState",
    "HelpCenterOutlineState",
    
    # Transactional
    "SalesPageOutlineState",
    "PricingPageOutlineState",
    "SignupPageOutlineState",
    "DemoPageOutlineState",
    "CouponPageOutlineState",
    "CheckoutPageOutlineState",
    "LandingPageOutlineState",
    "ServicePageOutlineState",
]
