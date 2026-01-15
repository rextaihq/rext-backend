from typing import List, Optional, Literal, Any
from typing_extensions import TypedDict,Annotated
import operator


class ContentSection(TypedDict):
    heading: str
    description: str
    key_points: List[str]
    suggested_word_count: Optional[int]


class ContentOutline(TypedDict):
    title: str
    brief: str
    sections: List[ContentSection]
    target_audience: List[str]
    tone: str
    keywords_to_include: List[str]

    status: Literal["approved", "rejected"]
    rejected_reason: Annotated[Optional[str],operator.add]


class ContentDraft(TypedDict):
    title: str
    body_markdown: str
    word_count: int
    sections_completed: List[str]

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

# On-Page SEO Scoring
class SEOCheckItem(TypedDict):
    """Individual SEO check with status."""
    category: str  # e.g., "title_optimization", "meta_description"
    label: str     # Human-readable label (e.g., "Focus keyword in H1")
    status: Literal["pass", "warning", "fail"]  # Visual indicator
    score: float   # Score for this check
    max_score: float  # Maximum possible score
    message: Optional[str]  # Detailed message/issue
    
class OnPageMetrics(TypedDict):
    """
    Complete on-page SEO scoring metrics.
    Designed to match UI requirements with status, checks, and optimization count.
    """
    # Overall Score
    score: float            # Score as percentage (0-100) - e.g., 92
    overall_score: float    # Actual score out of max_score
    max_score: float        # Maximum possible score (100)
    passed: bool           # Whether score meets 70% threshold
    
    # Status Display
    status_message: str    # e.g., "Almost Perfect!", "Needs Improvement", "Excellent!"
    optimizations_needed: int  # Number of items that need fixing
    
    # Individual Checks (for UI list)
    checks: List[SEOCheckItem]  # All check items with pass/warning/fail status
    
    # Detailed Breakdown (for advanced view)
    all_issues: List[str]  # All issues found
    breakdown: dict[str, Any]  # Detailed breakdown by category

class ContentReview(TypedDict, total=False):
    readability_metrics: ReadabilityMetrics
    # SEO metrics are hidden - on_page_metrics is optional
    on_page_metrics: Optional[OnPageMetrics]


class FinalContent(TypedDict):
    title: str
    body_markdown: str

    meta_title: str
    meta_description: str
    tags: List[str]

    primary_keyword: Optional[str]
    secondary_keywords: Optional[List[str]]
    word_count: int
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
    topics: List[str]
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

    # Error handling
    error: Optional[str]