# from typing import Literal
# from pydantic import Field
from src.flow.model.structure.outlines.base import BaseOutline, Section, Fact  # noqa: F401


# class BlogOutline(BaseOutline):
#     schema_type: Literal["Article", "HowTo", "FAQPage", "BlogPosting"] = Field(
#         default="Article",
#         description="Primary schema.org type for structured data."
#     )
#     target_word_count: int = Field(
#         ge=800,
#         le=5000,
#         description="Target word count for the complete article."
#     )


from typing import List, Optional, Literal
from pydantic import BaseModel, Field


# -------------------------
# HERO / CONTENT POSITIONING
# -------------------------

class BlogHero(BaseModel):
    headline: str = Field(description="SEO-optimized H1 title")
    subheadline: str = Field(description="Clarifies value + intent satisfaction")

    hook: Optional[str] = Field(
        default=None,
        description="Attention-grabbing opening angle"
    )


# -------------------------
# SEARCH INTENT MODEL (CRITICAL IN 2026 SEO)
# -------------------------

class SearchIntent(BaseModel):
    intent_type: Literal[
        "informational",
        "navigational_support",
        "educational",
        "problem_solving"
    ]
    user_goal: List[str]
    expected_outcome: str


# -------------------------
# TOPICAL AUTHORITY MODEL
# -------------------------

class TopicCluster(BaseModel):
    pillar_topic: Optional[str]
    supporting_topics: List[str]
    semantic_keywords: List[str]


# -------------------------
# CONTENT STRUCTURE (HIERARCHICAL SECTIONS)
# -------------------------

class Section(BaseModel):
    heading: str
    heading_level: Literal["H2", "H3", "H4"]
    purpose: str
    key_points: List[str]


class ContentStructure(BaseModel):
    sections: List[Section]


# -------------------------
# KNOWLEDGE DEPTH LAYERS
# -------------------------

class KnowledgeDepth(BaseModel):
    beginner_explanation: Optional[str]
    intermediate_depth: Optional[str]
    advanced_insight: Optional[str]


# -------------------------
# EEAT SIGNALS (VERY IMPORTANT IN 2026 SEO)
# -------------------------

class EEATSignals(BaseModel):
    experience_signals: List[str]
    expertise_signals: List[str]
    authority_signals: List[str]
    trust_signals: List[str]


# -------------------------
# FAQ + SNIPPET TARGETING
# -------------------------

class FAQItem(BaseModel):
    question: str
    answer: str


class FAQSection(BaseModel):
    faqs: List[FAQItem]


# -------------------------
# FEATURED SNIPPET OPTIMIZATION
# -------------------------

class SnippetTarget(BaseModel):
    query: str
    answer_format: Literal["definition", "list", "steps", "table"]
    content: str


class SnippetSection(BaseModel):
    snippets: List[SnippetTarget]


# -------------------------
# MEDIA STRATEGY (2026 CONTENT UX STANDARD)
# -------------------------

class MediaSuggestion(BaseModel):
    type: Literal["image", "diagram", "chart", "video"]
    description: str
    placement: str


class MediaPlan(BaseModel):
    media_items: List[MediaSuggestion]


# -------------------------
# INTERNAL LINKING STRATEGY (TOPICAL AUTHORITY ENGINE)
# -------------------------

class InternalLink(BaseModel):
    anchor_text: str
    target_page: str
    purpose: Optional[str]


class InternalLinking(BaseModel):
    links: List[InternalLink]


# -------------------------
# EXTERNAL REFERENCES (TRUST BOOSTER)
# -------------------------

class ExternalReference(BaseModel):
    source_name: str
    url: Optional[str]
    reason: str


class References(BaseModel):
    sources: List[ExternalReference]


# -------------------------
# CONTENT ENGAGEMENT SYSTEM
# -------------------------

class EngagementElement(BaseModel):
    type: Literal["example", "analogy", "case_study", "story", "statistic"]
    content: str


class EngagementPlan(BaseModel):
    elements: List[EngagementElement]


# -------------------------
# SEO METADATA STRATEGY
# -------------------------

class SEOPlan(BaseModel):
    focus_keyphrase: str
    keywords_to_include: List[str] = Field(
        default_factory=list,
        description="Secondary and long-tail keywords to naturally incorporate throughout the page."
    )
    secondary_keywords: List[str]
    search_variants: List[str]
    title_variations: Optional[List[str]]


# -------------------------
# CTA SYSTEM (LIGHT IN INFORMATIONAL CONTENT)
# -------------------------

class CTASection(BaseModel):
    primary_cta: Optional[str]
    secondary_cta: Optional[str]
    informational_cta: Optional[str] = Field(
        default="Learn more related topics"
    )


# -------------------------
# FINAL BLOG OUTLINE SCHEMA
# -------------------------

class BlogOutline(BaseModel):
    # Core metadata
    title: str
    slug_suggestion: str = Field(pattern=r"^[a-z0-9-]+$")

    target_audience: List[str]
    tone: Literal[
        "Informative",
        "Educational",
        "Authoritative",
        "Conversational",
        "Analytical"
    ]

    # Core SEO + intent system
    seo: SEOPlan
    search_intent: SearchIntent

    # Content foundation
    hero: BlogHero
    topic_cluster: TopicCluster

    # Structure (core content engine)
    structure: ContentStructure

    # Depth layering (2026 knowledge model)
    knowledge_depth: KnowledgeDepth

    # Authority building
    eeat: EEATSignals

    # Engagement system
    engagement: EngagementPlan

    # Snippet optimization (AI search + Google SERP)
    snippets: SnippetSection

    # FAQ system
    faqs: FAQSection

    # Media system
    media: MediaPlan

    # Internal linking (topical authority)
    internal_links: InternalLinking

    # External references
    references: References

    # CTA system (light)
    cta: CTASection

    # Optimization Layer (2026 informational content standard)
    content_goal: Literal[
        "educate_user",
        "rank_on_search",
        "build_authority",
        "answer_query_completely"
    ]

    target_reading_time_minutes: Optional[int] = Field(
        default=6,
        description="Optimal reading depth for informational blogs"
    )

    target_word_count: int = Field(
        default=1200,
        ge=800,
        le=2000,
        description="Blog depth depends on topic complexity"
    )