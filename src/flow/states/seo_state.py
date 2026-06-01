from __future__ import annotations

from typing_extensions import Annotated, Any, Literal, Optional, TypedDict

from src.flow.states.reducers.custom_reducer import merge_dicts


# 3. Content Pattern Analysis
class ContentPatternState(TypedDict):
    content_type: Literal[
        "blog",
        "listicle",
        "landing_page",
        "documentation",
        "comparison"
    ]
    avg_word_count: int
    common_headings: list[str]
    heading_depth: int
    media_usage: dict[str, int]  # images, tables, videos
    schema_types: list[str]


# 5. Authority & Trust Signals
class AuthorityState(TypedDict):
    avg_domain_strength: float
    dominant_domains: list[str]
    brand_presence: bool
    freshness_bias: bool
    authority_level: Literal["low", "medium", "high"]


#  Title Recommendation State
class TitleRecommendation(TypedDict):
    """Individual title recommendation with scoring."""
    title: str
    score: float
    char_count: int
    word_count: int
    reasons: list[str]
    rank: int


class KeywordRecommendationState(TypedDict):
    """Keyword recommendation result state."""
    original_title: str
    selected_keyword: str
    recommendations: list[str]
    is_changed: bool
    library_key: Optional[str]
    error: Optional[str]

class SERPBacklinks(TypedDict):
    keyword: str
    search_volume: int
    keyword_difficulty: int
    backlinks: int
    referring_domains: int
    dofollow_links: int
    images: bool
    videos: bool
    discussions_and_forums:bool
    main_intent: str
    foreign_intent: str



# 7. Keyword Clustering State
class KeywordCluster(TypedDict, total=False):
    """Cluster of semantically related keywords (Semrush/Ahrefs-style topic group)."""
    cluster_name: str
    keywords: list[dict[str, Any]]
    total_score: float
    main_intent: Optional[str]
    topic_theme: Optional[str]
    rationale: Optional[str]
    likely_serp_page_type: Optional[str]
    recommended_heading: Optional[str]
    outline_placement: Optional[str]
    page_fit_valid: Optional[bool]
    intent_match_score: Optional[float]
    serp_overlap_score: Optional[float]
    content_type_fit_score: Optional[float]
    cluster_strength_score: Optional[float]
    page_fit_score: Optional[float]
    topic_promise_score: Optional[float]
    overall_score: Optional[float]
    quality_scores: Optional[dict[str, float]]
    outline_mapping: Optional[dict[str, Any]]


class SEORESULT(TypedDict, total=False):
    """SEO analysis result - fields are optional as they may be populated by different nodes."""
    serp_backlinks: Annotated[SERPBacklinks, merge_dicts]
    keyword_recommendations: KeywordRecommendationState
    keyword_clusters: list[KeywordCluster]
    intent_type: str
    keyword_iteration_count: int
