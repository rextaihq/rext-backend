from __future__ import annotations

import operator
from typing_extensions import Annotated, Any, Literal, Optional, TypedDict

IssueLevel = Literal["CRITICAL", "ERROR", "WARNING", "INFO"]


class ContentSection(TypedDict):
    heading: str
    description: str
    key_points: list[str]
    suggested_word_count: Optional[int]


class ContentOutline(TypedDict):
    title: str
    brief: str
    sections: list[ContentSection]
    target_audience: list[str]
    tone: str
    keywords_to_include: list[str]

    status: Literal["approved", "rejected"]
    rejected_reason: Annotated[Optional[str], operator.add]


class ContentDraft(TypedDict):
    title: str
    body_markdown: str
    word_count: int
    sections_completed: list[str]

    status: Literal["approved", "rejected"]
    rejected_reason: Optional[str]


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


class FinalContent(TypedDict):
    title: str
    html_content: str
    body_markdown: str
    
    meta_title: str
    meta_description: str
    tags: list[str]

    primary_keyword: Optional[str]
    secondary_keywords: Optional[list[str]]
    word_count: int
    humanized_title: Optional[str]
    humanized_introduction: Optional[str]
    humanized_body_markdown: Optional[str]
    
    status: Literal["approved", "rejected", "draft"]
    rejected_reason: Optional[str]

    # WordPress publishing fields
    wordpress_post_id: Optional[int]
    wordpress_link: Optional[str]
    publish_error: Optional[str]


class CONTENT(TypedDict, total=False):
    """
    Main LangGraph state for AI-powered SEO content engine
    """

    # Core artifact
    topics: list[str]
    selected_topic: str
    outline: ContentOutline
    review: ContentReview
    final_content: FinalContent

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
    content_type: Literal[
        "article",
        "blog",
        "report",
        "whitepaper",
    ]

    # Post-review action tracking
    action: Optional[Literal["publish", "edit", "save"]]
    site_id: Optional[str]

    # Error handling
    error: Optional[str]