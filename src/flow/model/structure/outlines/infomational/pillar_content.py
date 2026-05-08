# from typing import List, Optional, Literal
# from pydantic import BaseModel, Field, conlist


# class ImageSuggestion(BaseModel):
#     """Suggested image or illustration for a section."""
    
#     description: str = Field(
#         description="Description of what the image should show."
#     )
#     alt_text_template: str = Field(
#         description="Template for SEO-optimized alt text."
#     )
#     section: str = Field(
#         description="Which section this image belongs to."
#     )


# class LinkSuggestion(BaseModel):
#     """Suggested link with context."""
    
#     anchor_text: str = Field(description="Suggested anchor text.")
#     link_type: Literal["internal", "outbound"] = Field(
#         description="Type of link to suggest."
#     )
#     context: str = Field(
#         description="Context about what this link should point to."
#     )
#     section: str = Field(
#         description="Which section this link should appear in."
#     )


# class Fact(BaseModel):
#     """Verifiable fact or statistic with source citation context."""
    
#     text: str = Field(description="The factual statement or statistic.")


# class PillarSection(BaseModel):
#     heading: str = Field(description="Section heading text.")
#     heading_level: Literal["H2", "H3"] = Field(description="Heading level.")
#     description: str = Field(description="Comprehensive coverage summary for this section.")
#     key_points: conlist(str, min_length=2, max_length=8)
#     subtopic_cluster: Optional[List[str]] = Field(default_factory=list, description="Related topics or clusters this section might link to.")
#     facts: Optional[List[Fact]] = Field(default_factory=list, description="Statistics or data points to include.")


# class PillarContentOutline(BaseModel):
#     title: str = Field(description="SEO-optimized pillar article title starting with the focus keyphrase.")
#     slug_suggestion: str = Field(
#         pattern=r"^[a-z0-9-]+$",
#         description="Suggested URL slug."
#     )
#     brief: str = Field(description="Overall mission statement for this ultimate guide/pillar content.")
    
#     # Topic Authority Strategy
#     focus_keyphrase: str = Field(
#         description="The primary broad focus keyphrase (e.g., 'Content Marketing')."
#     )
#     keywords_to_include: conlist(str, min_length=5)
#     related_clusters: List[str] = Field(description="Other subtopics that this pillar piece aims to govern.")
    
#     # Structure
#     sections: conlist(PillarSection, min_length=6, max_length=15)
#     faqs: Optional[List[str]] = Field(default_factory=list, description="Extensive list of common questions.")
    
#     # Images Planning
#     image_suggestions: List[ImageSuggestion] = Field(
#         min_length=3,
#         description="High-quality images/graphics to keep the reader engaged (min 3)."
#     )
    
#     # Links Planning (Focus on Topic Clusters)
#     link_suggestions: List[LinkSuggestion] = Field(
#         min_length=4,
#         description="Significant internal/external linking (min 4)."
#     )
    
#     # Schema
#     schema_type: Literal["Article", "WebPage", "FAQPage"] = Field(
#         default="Article",
#         description="Primary schema.org type."
#     )
    
#     # Content Strategy
#     target_audience: List[str]
#     tone: Literal[
#     "Professional", "Conversational", "Authoritative", "Friendly", 
#     "Encouraging", "Neutral", "Persuasive", "Analytical", 
#     "Direct", "Action-oriented", "Trustworthy", "Urgent"
#     ]
#     target_word_count: int = Field(ge=1500, le=10000)


from typing import List, Optional, Literal
from pydantic import BaseModel, Field


# -------------------------
# HERO / AUTHORITY POSITIONING
# -------------------------

class PillarHero(BaseModel):
    headline: str = Field(description="Authority-driven title (e.g., 'Complete Guide to X in 2026')")
    subheadline: str = Field(description="Defines scope and depth coverage")

    authority_statement: str = Field(
        description="Why this page is the definitive resource on the topic"
    )


# -------------------------
# TOPIC AUTHORITY CONTEXT (CORE 2026 SEO MODEL)
# -------------------------

class TopicAuthority(BaseModel):
    primary_topic: str
    topic_scope: List[str]
    search_intent_coverage: List[str]


# -------------------------
# CONTENT CLUSTER ARCHITECTURE (VERY IMPORTANT)
# -------------------------

class ClusterTopic(BaseModel):
    cluster_name: str
    purpose: str
    subtopics: List[str]


class ClusterArchitecture(BaseModel):
    clusters: List[ClusterTopic]


# -------------------------
# PILLAR STRUCTURE (HIERARCHICAL CONTENT ENGINE)
# -------------------------

class Section(BaseModel):
    heading: str
    heading_level: Literal["H2", "H3", "H4"]
    purpose: str
    key_points: List[str]


class ContentStructure(BaseModel):
    sections: List[Section]


# -------------------------
# SEMANTIC COVERAGE MAP (2026 AI SEO REQUIREMENT)
# -------------------------

class SemanticCoverage(BaseModel):
    covered_entities: List[str]
    covered_concepts: List[str]
    missing_gaps: Optional[List[str]]


# -------------------------
# INTERNAL LINKING STRATEGY (TOPICAL AUTHORITY ENGINE)
# -------------------------

class InternalLink(BaseModel):
    anchor_text: str
    target_page: str
    link_type: Literal[
        "pillar_to_cluster",
        "cluster_to_pillar",
        "cluster_to_cluster"
    ]


class InternalLinking(BaseModel):
    links: List[InternalLink]


# -------------------------
# ENTITY GRAPH (AI SEARCH OPTIMIZATION)
# -------------------------

class EntityRelation(BaseModel):
    entity: str
    relation: str
    connected_entity: str


class EntityGraph(BaseModel):
    relations: List[EntityRelation]


# -------------------------
# FAQ SYSTEM (SNIPPET + AI OVERVIEW OPTIMIZATION)
# -------------------------

class FAQItem(BaseModel):
    question: str
    answer: str


class FAQSection(BaseModel):
    faqs: List[FAQItem]


# -------------------------
# SNIPPET TARGETING (AI SEARCH OPTIMIZATION)
# -------------------------

class SnippetTarget(BaseModel):
    query: str
    answer_format: Literal["definition", "list", "steps", "table"]
    optimized_answer: str


class SnippetSection(BaseModel):
    snippets: List[SnippetTarget]


# -------------------------
# EEAT SIGNALS (CRITICAL FOR AUTHORITY PAGES)
# -------------------------

class EEATSignals(BaseModel):
    experience_signals: List[str]
    expertise_signals: List[str]
    authority_signals: List[str]
    trust_signals: List[str]


# -------------------------
# CONTENT DEPTH MODEL (VERY IMPORTANT IN 2026)
# -------------------------

class DepthLayer(BaseModel):
    level: Literal["overview", "intermediate", "advanced"]
    explanation: str


class ContentDepth(BaseModel):
    layers: List[DepthLayer]


# -------------------------
# MEDIA STRATEGY (ENHANCED UX)
# -------------------------

class MediaItem(BaseModel):
    type: Literal["diagram", "flowchart", "table", "image", "video"]
    description: str
    placement: str


class MediaPlan(BaseModel):
    media: List[MediaItem]


# -------------------------
# USER JOURNEY ALIGNMENT
# -------------------------

class UserJourney(BaseModel):
    stage: Literal["awareness", "consideration", "decision"]
    content_focus: str


# -------------------------
# AUTHORITY SUMMARY
# -------------------------

class AuthoritySummary(BaseModel):
    key_takeaways: List[str]
    topic_mastery_statement: str


# -------------------------
# FINAL PILLAR CONTENT SCHEMA
# -------------------------

class PillarContentOutline(BaseModel):
    # Core metadata
    title: str
    slug_suggestion: str = Field(pattern=r"^[a-z0-9-]+$")
    focus_keyphrase: str
    keywords_to_include: List[str] = Field(
        default_factory=list,
        description="Secondary and long-tail keywords to naturally incorporate throughout the page."
    )

    target_audience: List[str]
    tone: Literal[
        "Authoritative",
        "Educational",
        "Analytical",
        "Comprehensive",
        "Trustworthy"
    ]

    # Authority foundation
    hero: PillarHero
    topic_authority: TopicAuthority

    # Core architecture system
    cluster_architecture: ClusterArchitecture

    # Content structure (pillar body)
    structure: ContentStructure

    # Semantic intelligence layer
    semantic_coverage: SemanticCoverage
    entity_graph: EntityGraph

    # Depth layering system
    content_depth: ContentDepth

    # SEO + AI optimization layers
    internal_linking: InternalLinking
    snippets: SnippetSection
    faqs: FAQSection

    # Authority building system
    eeat: EEATSignals

    # UX enhancement
    media: MediaPlan

    # User journey mapping
    user_journey: UserJourney

    # Final authority summary
    summary: AuthoritySummary

    # Optimization Layer (2026 informational SEO standard)
    content_goal: Literal[
        "establish_topic_authority",
        "cover_entire_subject",
        "support_cluster_ecosystem",
        "dominate_search_topic"
    ]

    success_metric: str = Field(
        default="Page becomes central authority hub for entire topic cluster"
    )

    target_word_count: int = Field(
        default=3000,
        ge=4500,
        le=6000,
        description="Pillar content is long-form authority content"
    )