from typing import List, Dict, Any, Optional, Literal
from typing_extensions import TypedDict


# ---------------------------------------------------------
# 1. Search Intent Analysis
# ---------------------------------------------------------

# class SearchIntentState(TypedDict):
#     primary_intent: Literal[
#         "informational",
#         "commercial",
#         "transactional",
#         "navigational"
#     ]
#     secondary_intents: List[str]
#     confidence: float
#     intent_signals: Dict[str, int]  # keyword → frequency


# # ---------------------------------------------------------
# # 2. Keyword Difficulty
# # ---------------------------------------------------------

# class KeywordDifficultyState(TypedDict):
#     keywords: List[str]
#     difficulty_level: Literal["easy", "medium", "hard", "very_hard"]
#     serp_competition: int
#     authority_barrier: Literal["low", "medium", "high"]


# # ---------------------------------------------------------
# # 3. Content Pattern Analysis
# # ---------------------------------------------------------
# class ContentPatternState(TypedDict):
#     content_type: Literal[
#         "blog",
#         "listicle",
#         "landing_page",
#         "documentation",
#         "comparison"
#     ]
#     avg_word_count: int
#     common_headings: List[str]
#     heading_depth: int
#     media_usage: Dict[str, int]  # images, tables, videos
#     schema_types: List[str]


# ---------------------------------------------------------
# 4. Content Gap Analysis
# ---------------------------------------------------------

# class ContentGapState(TypedDict):
#     missing_topics: List[str]
#     missing_questions: List[str]
#     weak_coverage_areas: List[str]
#     recommended_sections: List[str]


# ---------------------------------------------------------
# 5. Authority & Trust Signals
# ---------------------------------------------------------

# class AuthorityState(TypedDict):
#     avg_domain_strength: float
#     dominant_domains: List[str]
#     brand_presence: bool
#     freshness_bias: bool
#     authority_level: Literal["low", "medium", "high"]


# ---------------------------------------------------------
# 6. SERP Feature Impact
# ---------------------------------------------------------

# class SERPFeatureImpactState(TypedDict):
#     features_present: List[str]
#     ctr_loss_estimate: float
#     blocking_features: List[str]
#     opportunity_features: List[str]


# # ---------------------------------------------------------
# # 7. SEO Strategy (Actionable Output)
# # ---------------------------------------------------------

# class SEOStrategyState(TypedDict):
#     target_intent: str
#     recommended_content_type: str
#     ideal_word_count: int
#     priority_topics: List[str]
#     questions_to_answer: List[str]
#     difficulty: str
#     ranking_time_estimate: str
#     content_angle: str

# class ExtractedKeyword(TypedDict):
#     """Individual extracted keyword with TF-IDF scoring."""
#     keyword: str
#     score: float  # Normalized 0-100 score
#     raw_tfidf: float  # Raw TF-IDF score
#     rank: int
#     word_count: int
#     type: Literal["head", "body", "long-tail"]
#     in_query: bool
#     in_topics: bool

# class ExtractedKeywordsState(TypedDict):
#     """Collection of extracted keywords categorized by type."""
#     all: List[ExtractedKeyword]
#     head: List[ExtractedKeyword]
#     body: List[ExtractedKeyword]
#     long_tail: List[ExtractedKeyword]
#     total_count: int
#     query: str
#     extraction_method: str
#     sources: Dict[str, int]

# ---------------------------------------------------------
# 8. Final SEO Engine Result State
# ---------------------------------------------------------

# class SEORESULT(TypedDict, total=False):
#     """SEO analysis result - fields are optional as they may be populated by different nodes."""
#     extracted_keywords: ExtractedKeywordsState
#     keyword_difficulty: KeywordDifficultyState
#     intent: SearchIntentState
#     content_pattern: ContentPatternState
#     content_gaps: ContentGapState
#     authority: AuthorityState
#     serp_features: SERPFeatureImpactState
#     seo_strategy: SEOStrategyState


# src/flow/states/seo_state.py

from typing import List, Dict, Literal
from typing_extensions import TypedDict


class KeywordScoreState(TypedDict):
    score: float
    strength: Literal["low", "medium", "high"]
    signals: Dict[str, float]


class CompetitorGapScoreState(TypedDict):
    gap_score: float
    missing_topics: List[str]
    missing_questions: List[str]
    weak_areas: List[str]


class SEOOpportunityState(TypedDict):
    opportunity_score: float
    level: Literal["low", "medium", "high"]
    reasoning: List[str]


class ArticleDecisionState(TypedDict):
    generate_article: bool
    confidence: float
    reason: str


class SEORESULT(TypedDict, total=False):
    extracted_keywords: Dict
    keyword_difficulty: Dict
    keyword_score: KeywordScoreState
    competitor_gap: CompetitorGapScoreState
    seo_opportunity: SEOOpportunityState
    article_decision: ArticleDecisionState
