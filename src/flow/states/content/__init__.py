from typing import Union

from .informational import (
    BlogContent,
    HowToGuideContent,
    ExplainerContent,
    PillarContent,
    ChecklistContent,
    TutorialContent,
    FAQContent,
    WhitePaperContent,
    CaseStudyContent,
    GlossaryContent,
    ResourceListContent,
)

from .commercial import (
    ComparisonContentState,
    BestToolsContentState,
    AlternativesContentState,
    InDepthReviewContentState,
    ProsConsContentState,
    ProductRoundupContentState,
    BuyingGuideContentState,
)

from .navigational import (
    BrandPageContentState,
    ProductHomepageContentState,
    FeatureOverviewContentState,
    DocumentationContentState,
    LoginGuideContentState,
    ContactUsContentState,
    AboutUsContentState,
    HelpCenterContentState,
)

from .transactional import (
    SalesPageContentState,
    PricingPageContentState,
    SignupPageContentState,
    DemoPageContentState,
    CouponPageContentState,
    CheckoutPageContentState,
    LandingPageContentState,
    ServicePageContentState,
)

FinalContentState = Union[
    # Informational
    BlogContent,
    HowToGuideContent,
    ExplainerContent,
    PillarContent,
    ChecklistContent,
    TutorialContent,
    FAQContent,
    WhitePaperContent,
    CaseStudyContent,
    GlossaryContent,
    ResourceListContent,
    
    # Commercial
    ComparisonContentState,
    BestToolsContentState,
    AlternativesContentState,
    InDepthReviewContentState,
    ProsConsContentState,
    ProductRoundupContentState,
    BuyingGuideContentState,
    
    # Navigational
    BrandPageContentState,
    ProductHomepageContentState,
    FeatureOverviewContentState,
    DocumentationContentState,
    LoginGuideContentState,
    ContactUsContentState,
    AboutUsContentState,
    HelpCenterContentState,
    
    # Transactional
    SalesPageContentState,
    PricingPageContentState,
    SignupPageContentState,
    DemoPageContentState,
    CouponPageContentState,
    CheckoutPageContentState,
    LandingPageContentState,
    ServicePageContentState,
]

__all__ = [
    "FinalContentState",
    
    # Informational
    "BlogContent",
    "HowToGuideContent",
    "ExplainerContent",
    "PillarContent",
    "ChecklistContent",
    "TutorialContent",
    "FAQContent",
    "WhitePaperContent",
    "CaseStudyContent",
    "GlossaryContent",
    "ResourceListContent",
    
    # Commercial
    "ComparisonContentState",
    "BestToolsContentState",
    "AlternativesContentState",
    "InDepthReviewContentState",
    "ProsConsContentState",
    "ProductRoundupContentState",
    "BuyingGuideContentState",
    
    # Navigational
    "BrandPageContentState",
    "ProductHomepageContentState",
    "FeatureOverviewContentState",
    "DocumentationContentState",
    "LoginGuideContentState",
    "ContactUsContentState",
    "AboutUsContentState",
    "HelpCenterContentState",
    
    # Transactional
    "SalesPageContentState",
    "PricingPageContentState",
    "SignupPageContentState",
    "DemoPageContentState",
    "CouponPageContentState",
    "CheckoutPageContentState",
    "LandingPageContentState",
    "ServicePageContentState",

    # Main Engine State
    "CONTENT",
    "ContentReview",
    "TrustScore",
    "SeokarSEOState",
    "ReadabilityMetrics",
    "IssueSummary",
    "PageMetadata",
    "ContentQuality",
    "SEOIssue",
]

from typing_extensions import Any, Literal, Optional, TypedDict
from src.flow.states.outline import OutlineState

IssueLevel = Literal["CRITICAL", "ERROR", "WARNING", "INFO"]


# Readability Metrics
class ReadabilityMetrics(TypedDict):
    flesch_reading_ease: float
    flesch_kincaid_grade: float
    gunning_fog_index: float
    smog_index: float
    automated_readability_index: float
    coleman_liau_index: float
    dale_chall_score: float


# On-Page SEO

class SEOIssue(TypedDict):
    type: str                # e.g. "Image Alt Text"
    level: IssueLevel        # WARNING / ERROR / CRITICAL
    message: str             # Short issue summary
    details: str             # Full explanation
    recommendation: str      # Fix suggestion


class PageMetadata(TypedDict):
    title: str
    meta_description: str
    canonical_url: str


class ContentQuality(TypedDict):
    top_keywords: dict[str, str]


class IssueSummary(TypedDict):
    critical: int
    errors: int
    warnings: int


class SeokarSEOState(TypedDict):
    """
    Raw SEO analysis state produced by Seokar.
    No UI logic, no scoring assumptions.
    """

    # Core Score
    seo_health_score: float
    # Issue Summary
    issue_summary: IssueSummary

    # Page Metadata
    page: PageMetadata

    # Issues
    issues: list[SEOIssue]

    # Content Quality Signals
    content_quality: ContentQuality


# Trust Score (E-E-A-T & Credibility Metrics)
class TrustScore(TypedDict):
    score: float                # Overall trust score (0-100)
    author_credibility: float    # Verified author identity, bio, and historical reputation
    expertise: float            # Depth of knowledge and credentials shown in the content
    authority: float            # Domain authority and external mentions of the topic
    trustworthiness: float      # Transparency, safety, and reliability of the platform
    citations_references: float # Quality and quantity of external links and expert citations
    content_accuracy: float     # Fact-checking against known reliable sources
    freshness: float            # How up-to-date the information and data points are
    transparency: float         # Clear disclosures, affiliate links transparency, and contact info
    spam_signals: float         # Absence of aggressive ads, manipulative links, or duplicate content
    technical_trust: float      # HTTPS, mobile-friendliness, and site security signals


class ContentReview(TypedDict, total=False):
    readability_metrics: ReadabilityMetrics
    # SEO metrics are hidden - on_page_metrics is optional
    on_page_metrics: Optional[SeokarSEOState]
    trust_score: Optional[TrustScore]


class CONTENT(TypedDict, total=False):
    """
    Main LangGraph state for AI-powered SEO content engine
    """
    # Core artifact
    topics: list[str]
    selected_topic: str
    outline: OutlineState
    review: ContentReview
    final_content: FinalContentState

    # Workflow control
    status: Literal[
        "planning",
        "drafting",
        "reviewing",
        "editing",
        "optimizing",
        "completed",
        "failed",
    ]
    content_type: str

    # Post-review action tracking
    action: Optional[Literal["publish", "edit", "save"]]
    site_id: Optional[str]

    # Error handling
    error: Optional[str]
