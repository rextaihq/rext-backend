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


# 4. Content Gap Analysis

class ContentGapState(TypedDict):
    missing_topics: list[str]
    missing_questions: list[str]
    weak_coverage_areas: list[str]
    recommended_sections: list[str]


# 5. Authority & Trust Signals
class AuthorityState(TypedDict):
    avg_domain_strength: float
    dominant_domains: list[str]
    brand_presence: bool
    freshness_bias: bool
    authority_level: Literal["low", "medium", "high"]


# 6. SERP Feature Impact
class SERPFeatureImpactState(TypedDict):
    features_present: list[str]
    ctr_loss_estimate: float
    blocking_features: list[str]
    opportunity_features: list[str]


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


class SEOOpportunityState(TypedDict):
    opportunity_score: int
    opportunity_level: Literal["low", "medium", "high"]
    key_drivers: dict[str, Any]


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



class SEORESULT(TypedDict, total=False):
    """SEO analysis result - fields are optional as they may be populated by different nodes."""
    serp_backlinks: Annotated[SERPBacklinks, merge_dicts]
    keyword_recommendations: KeywordRecommendationState
    content_gaps: ContentGapState
    serp_features: SERPFeatureImpactState
    seo_opportunity: SEOOpportunityState 
    keyword_iteration_count: int
