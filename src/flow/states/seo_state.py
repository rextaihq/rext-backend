from typing import List, Dict, Any, Optional, Literal
from typing_extensions import TypedDict


# ---------------------------------------------------------
# 1. Search Intent Analysis
# ---------------------------------------------------------

class SearchIntentState(TypedDict):
    primary_intent: Literal[
        "informational",
        "commercial",
        "transactional",
        "navigational"
    ]
    secondary_intents: List[str]
    confidence: float
    intent_signals: Dict[str, int]  # keyword → frequency


# ---------------------------------------------------------
# 2. Keyword Difficulty (Unified)
# ---------------------------------------------------------

class KDBreakdown(TypedDict, total=False):
    link_score: float
    serp_score: float
    content_score: float
    context_modifier: float
    # Extended signals for Opportunity calculation
    brand_dominance: float
    freshness_pressure: float

class KeywordDifficultyState(TypedDict):
    keyword: str
    difficulty_score: float
    difficulty_level: Literal["easy", "medium", "hard", "very_hard"]
    breakdown: KDBreakdown
    notes: List[str]


# ---------------------------------------------------------
# 3. Content Pattern Analysis
# ---------------------------------------------------------
class ContentPatternState(TypedDict):
    content_type: Literal[
        "blog",
        "listicle",
        "landing_page",
        "documentation",
        "comparison"
    ]
    avg_word_count: int
    common_headings: List[str]
    heading_depth: int
    media_usage: Dict[str, int]  # images, tables, videos
    schema_types: List[str]


# ---------------------------------------------------------
# 4. Content Gap Analysis
# ---------------------------------------------------------

class ContentGapState(TypedDict):
    missing_topics: List[str]
    missing_questions: List[str]
    weak_coverage_areas: List[str]
    recommended_sections: List[str]


# ---------------------------------------------------------
# 5. Authority & Trust Signals
# ---------------------------------------------------------

class AuthorityState(TypedDict):
    avg_domain_strength: float
    dominant_domains: List[str]
    brand_presence: bool
    freshness_bias: bool
    authority_level: Literal["low", "medium", "high"]


# ---------------------------------------------------------
# 6. SERP Feature Impact
# ---------------------------------------------------------

class SERPFeatureImpactState(TypedDict):
    features_present: List[str]
    ctr_loss_estimate: float
    blocking_features: List[str]
    opportunity_features: List[str]


class ExtractedKeyword(TypedDict):
    """Individual extracted keyword with TF-IDF scoring."""
    keyword: str
    score: float  
    raw_tfidf: float  
    rank: int
    word_count: int
    in_query: bool
    in_topics: bool

class ExtractedKeywordsState(TypedDict):
    """Collection of extracted keywords categorized by type."""
    all: List[ExtractedKeyword]
    total_count: int
    query: str
    extraction_method: str
    sources: Dict[str, int]

# ---------------------------------------------------------
# 8. Final SEO Engine Result State
# ---------------------------------------------------------

#  Title Recommendation State
class TitleRecommendation(TypedDict):
    """Individual title recommendation with scoring."""
    title: str
    score: float
    char_count: int
    word_count: int
    reasons: List[str]
    rank: int

class KeywordRecommendationState(TypedDict):
    """Keyword recommendation result state."""
    original_title: str
    recommendations: List[TitleRecommendation]
    patterns_found: Dict[str, Any]
    top_keywords_used: List[str]
    total_competitors_analyzed: int
    is_changed: bool
    error: Optional[str]    
    
class SEOOpportunityState(TypedDict):
    opportunity_score: int
    opportunity_level: Literal["low", "medium", "high"]
    key_drivers: Dict[str, Any]

class SEOStrategyState(TypedDict):
    target_intent: str
    recommended_content_type: str
    ideal_word_count: int
    priority_topics: List[str]
    questions_to_answer: List[str]
    difficulty: str
    ranking_time_estimate: str
    content_angle: str

class SEORESULT(TypedDict, total=False):
    """SEO analysis result - fields are optional as they may be populated by different nodes."""
    extracted_keywords: ExtractedKeywordsState
    keyword_difficulty: KeywordDifficultyState
    keyword_recommendations: KeywordRecommendationState
    intent: SearchIntentState
    content_pattern: ContentPatternState
    content_gaps: ContentGapState
    authority: AuthorityState
    serp_features: SERPFeatureImpactState
    seo_strategy: SEOStrategyState
    seo_opportunity: SEOOpportunityState 
