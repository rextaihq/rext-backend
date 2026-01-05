from typing import List, Optional, Literal
from typing_extensions import TypedDict


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
    rejected_reason: Optional[str]


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

class ContentReview(TypedDict):
    seo_score: float
    readability_metrics: ReadabilityMetrics

    eeat_score: Optional[float]
    plagiarism_score: Optional[float]

    passed: bool

    missing_points: List[str]
    improvement_suggestions: List[str]


class FinalContent(TypedDict):
    title: str
    body_markdown: str

    meta_title: str
    meta_description: str
    tags: List[str]

    primary_keyword: Optional[str]
    secondary_keywords: Optional[List[str]]
    word_count: int
    status: Literal["approved", "rejected"]
    rejected_reason: Optional[str]


class CONTENT(TypedDict, total=False):
    """
    Main LangGraph state for AI-powered SEO content engine
    """

    # Core artifacts
    outline: ContentOutline
    draft: ContentDraft
    review: ContentReview
    final_content: FinalContent

    # Workflow control
    status: Literal[
        "planning",
        "drafting",
        "reviewing",
        "optimizing",
        "completed",
        "failed",
    ]

    # Retry management
    outline_retries: int
    draft_retries: int
    review_retries: int
    max_retries: int

    # Error handling
    error: Optional[str]