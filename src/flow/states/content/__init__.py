from typing import Union

from typing_extensions import Any, Literal, NotRequired, Optional, TypedDict

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
    # Quality gate (validate / repair / humanize)
    "ValidationCheckResult",
    "ContentValidation",
    "RepairAttempt",
    "SearchedResult",
    "GenerationMeta",
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


# Trust Score (E-E-A-T & Credibility Metrics)
class TrustScore(TypedDict):
    score: float  # Overall trust score (0-100)
    author_credibility: float  # Verified author identity, bio, and historical reputation
    expertise: float  # Depth of knowledge and credentials shown in the content
    authority: float  # Domain authority and external mentions of the topic
    trustworthiness: float  # Transparency, safety, and reliability of the platform
    citations_references: float  # Quality and quantity of external links and expert citations
    content_accuracy: float  # Fact-checking against known reliable sources
    freshness: float  # How up-to-date the information and data points are
    transparency: float  # Clear disclosures, affiliate links transparency, and contact info
    spam_signals: float  # Absence of ads, manipulative links, or duplicate content
    technical_trust: float  # HTTPS, mobile-friendliness, and site security signals


class ValidationCheckResult(TypedDict):
    """Result of a single deterministic quality check."""

    name: str
    passed: bool
    severity: Literal["blocking", "warning"]
    detail: str


class ContentValidation(TypedDict, total=False):
    """Result of running the full deterministic check suite once."""

    passed: bool
    # True when a blocking failure exists that the repair model owns. False when
    # the only failures are owned by humanization (word count) — routing reads
    # this, so a word-count-only failure never costs a repair call.
    repair_required: bool
    gave_up: bool
    failed_checks: list[ValidationCheckResult]  # blocking only
    # Blocking failures deferred to humanization rather than repair.
    deferred_checks: list[ValidationCheckResult]
    warnings: list[ValidationCheckResult]  # non-blocking (heuristic/best-effort)
    checked_at: str
    stage: Literal["pre_repair", "post_humanize"]
    validation_run_id: str


class _RepairAttemptRequired(TypedDict):
    attempt: int
    targeted_checks: list[str]
    at: str


class RepairAttempt(_RepairAttemptRequired, total=False):
    """One targeted repair pass, logged for observability and loop bounding."""

    # Whether the repaired content replaced the pre-repair content. A repair
    # that breaks a check that was passing is rejected rather than accepted.
    accepted: bool
    resolved_checks: list[str]
    unresolved_checks: list[str]
    regressed_checks: list[str]
    restored_links: list[str]


class SearchedResult(TypedDict):
    """A single Tavily search_tool result actually seen during this generation run.

    Real ground truth for citation-provenance checks — without this, a
    fact/outbound-link URL can never be distinguished from a fabricated one.
    """

    url: str
    title: str
    snippet: str
    # Set only on official-source records (entity_research.py).
    retrieved_at: NotRequired[str]
    published_date: NotRequired[str]
    entity: NotRequired[str]
    official_domain: NotRequired[str]
    is_brand: NotRequired[bool]


class GenerationMeta(TypedDict, total=False):
    """Metadata captured during generation that downstream nodes need but
    that isn't part of the article itself."""

    searched_results: list[SearchedResult]
    # Valid, relevant inline links (approved internal, verified citation, brand)
    # the article has carried at any accepted stage — the baseline
    # check_links_preserved compares against. See link_integrity.py.
    link_inventory: list[dict]


class ContentReview(TypedDict, total=False):
    readability_metrics: ReadabilityMetrics
    # SEO metrics are hidden - on_page_metrics is optional
    on_page_metrics: Optional[SeokarSEOState]
    trust_score: Optional[TrustScore]
    validation: ContentValidation
    final_validation: ContentValidation
    repair_attempts: int
    repair_history: list[RepairAttempt]


class CONTENT(TypedDict, total=False):
    """
    Main LangGraph state for AI-powered SEO content engine
    """

    # Core artifact
    topics: list[str]
    recommended_topic: Optional[str]
    selected_topic: str
    # The user's own query, pinned by topic_generation (re-pinned by
    # generate_outline) and read by every stage after it. Never a
    # model-generated substitute -- see
    # src/flow/engines/content/generation/focus_keyword.py.
    focus_keyword: str
    cluster_heading_map: ClusterHeadingMap
    outline: OutlineState
    review: ContentReview
    final_content: FinalContentState
    generation_meta: GenerationMeta
    credits_deducted: bool

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
