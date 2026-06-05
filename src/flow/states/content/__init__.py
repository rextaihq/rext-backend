from typing import Union

from typing_extensions import Any, Literal, Optional, TypedDict

from src.flow.states.outline import OutlineState

from .commercial import (
    AlternativesContentState,
    BestToolsContentState,
    BuyingGuideContentState,
    ComparisonContentState,
    InDepthReviewContentState,
    ProductRoundupContentState,
    ProsConsContentState,
)
from .informational import (
    BlogContent,
    CaseStudyContent,
    ChecklistContent,
    ExplainerContent,
    FAQContent,
    GlossaryContent,
    HowToGuideContent,
    PillarContent,
    ResourceListContent,
    TutorialContent,
    WhitePaperContent,
)
from .navigational import (
    AboutUsContentState,
    BrandPageContentState,
    ContactUsContentState,
    DocumentationContentState,
    FeatureOverviewContentState,
    HelpCenterContentState,
    LoginGuideContentState,
    ProductHomepageContentState,
)
from .transactional import (
    CheckoutPageContentState,
    CouponPageContentState,
    DemoPageContentState,
    LandingPageContentState,
    PricingPageContentState,
    SalesPageContentState,
    ServicePageContentState,
    SignupPageContentState,
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
    "ClusterHeadingMap",
    "ClusterHeadingMapSection",
]

IssueLevel = Literal["CRITICAL", "ERROR", "WARNING", "INFO"]


class ClusterHeadingMapSection(TypedDict, total=False):
    order: int
    heading_level: Literal["H2"]
    suggested_heading: str
    cluster_name: str
    topic_theme: str
    primary_keyword: str
    supporting_keywords: list[str]
    search_intent: str
    rationale: str
    h3_topics: list[str]
    mapped_h3_clusters: list[dict[str, Any]]
    questions_to_answer: list[str]
    quality_scores: dict[str, float]


class ClusterHeadingMap(TypedDict, total=False):
    enabled: bool
    skipped: bool
    reason: str
    content_type: str
    h1: dict[str, Any]
    h2_sections: list[ClusterHeadingMapSection]
    h3_sections: list[dict[str, Any]]
    body_copy_clusters: list[dict[str, Any]]
    additional_keywords: list[str]
    rules: list[str]
    content_type_guidance: str


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
    type: str  # e.g. "Image Alt Text"
    level: IssueLevel  # WARNING / ERROR / CRITICAL
    message: str  # Short issue summary
    details: str  # Full explanation
    recommendation: str  # Fix suggestion


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


# Trust Score (content-level E-E-A-T only)
class TrustScore(TypedDict, total=False):
    score: float
    trust_score: float
    status: str
    experience: float
    expertise: float
    authoritativeness: float
    trustworthiness: float
    signal_breakdown: dict[str, Any]
    reasoning: str
    recommendations: list[str]
    confidence: float
    rubric_version: str
    content_type: str
    scoring_scope: str


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
    cluster_heading_map: ClusterHeadingMap
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
