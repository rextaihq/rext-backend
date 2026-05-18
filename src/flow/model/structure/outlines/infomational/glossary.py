# from typing import List, Optional, Literal
# from pydantic import BaseModel, Field, conlist


# class GlossaryEntry(BaseModel):
#     """An individual term and its definition."""
#     term: str = Field(description="The term or phrase being defined.")
#     definition: str = Field(description="Clear and concise definition.")
#     examples: Optional[List[str]] = Field(default_factory=list, description="Examples of the term in use.")
#     related_terms: Optional[List[str]] = Field(default_factory=list, description="Terms related to this one.")


# class GlossarySection(BaseModel):
#     heading: str = Field(description="Alphabetical or category heading (e.g., 'A-C', 'Tech Terms').")
#     heading_level: Literal["H2", "H3"] = Field(description="Heading level.")
#     description: str = Field(description="Introduction to the terms in this section.")
#     entries: conlist(GlossaryEntry, min_length=2, max_length=20)


# class GlossaryOutline(BaseModel):
#     title: str = Field(description="SEO-optimized glossary title (e.g., '[Focus Keyphrase] Glossary').")
#     slug_suggestion: str = Field(
#         pattern=r"^[a-z0-9-]+$",
#         description="Suggested URL slug."
#     )
#     brief: str = Field(description="Target audience and the specific lexicon the glossary covers.")
    
#     # Context
#     focus_keyphrase: str = Field(
#         description="The primary domain or industry the glossary covers."
#     )
#     keywords_to_include: conlist(str, min_length=1)
    
#     # Structure
#     sections: conlist(GlossarySection, min_length=1, max_length=20)
    
#     # Navigation/A-Z Strategy
#     alphabetical_navigation: bool = Field(default=True, description="Whether to include A-Z navigation at the top.")
    
#     # Images Planning
#     image_suggestions: List[str] = Field(
#         description="Suggested header image or icons for categories (min 1)."
#     )
    
#     # Links Planning
#     link_suggestions: List[str] = Field(
#         description="Suggested internal links to in-depth guides for terms."
#     )
    
#     # Schema
#     schema_type: Literal["Article", "DefinedTermSet", "WebPage"] = Field(
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
#     target_word_count: int = Field(ge=500, le=5000)


from typing import List, Optional, Literal
from pydantic import BaseModel, Field


# -------------------------
# HERO / GLOSSARY POSITIONING
# -------------------------

class GlossaryHero(BaseModel):
    headline: str = Field(description="Main glossary title (e.g., 'AI & Machine Learning Glossary')")
    subheadline: str = Field(description="What domain or knowledge area this glossary covers")

    purpose_statement: str = Field(
        description="Why this glossary exists and what users will gain"
    )


# -------------------------
# DOMAIN CONTEXT (VERY IMPORTANT IN 2026 SEMANTIC SEO)
# -------------------------

class DomainContext(BaseModel):
    domain: str
    scope: List[str]
    target_users: List[str]


# -------------------------
# TERM DEFINITION (CORE UNIT)
# -------------------------

class GlossaryTerm(BaseModel):
    term: str
    simple_definition: str = Field(description="Plain-language explanation")

    detailed_definition: Optional[str]

    category: Optional[str]

    difficulty_level: Literal["basic", "intermediate", "advanced"]

    usage_context: Optional[str] = Field(
        description="Where/how this term is used in real-world scenarios"
    )

    examples: Optional[List[str]]


# -------------------------
# TERM RELATIONSHIPS (KNOWLEDGE GRAPH CORE)
# -------------------------

class TermRelationship(BaseModel):
    related_term: str
    relationship_type: Literal[
        "synonym",
        "opposite",
        "parent_concept",
        "child_concept",
        "depends_on",
        "commonly_confused_with"
    ]
    explanation: Optional[str]


class RelationshipMap(BaseModel):
    term: str
    relationships: List[TermRelationship]


# -------------------------
# TERM CLUSTERING (TOPIC ORGANIZATION)
# -------------------------

class TermCluster(BaseModel):
    cluster_name: str
    description: Optional[str]
    terms: List[str]


# -------------------------
# CONTEXTUAL EXAMPLES (CRITICAL FOR UNDERSTANDING)
# -------------------------

class ContextualExample(BaseModel):
    term: str
    scenario: str
    explanation: str


class ExampleSection(BaseModel):
    examples: List[ContextualExample]


# -------------------------
# COMMON MISUNDERSTANDINGS (IMPORTANT FOR ACCURACY)
# -------------------------

class Misconception(BaseModel):
    term: str
    incorrect_belief: str
    correct_explanation: str


class MisconceptionsSection(BaseModel):
    items: List[Misconception]


# -------------------------
# CROSS-REFERENCING (SEO + AI CONTEXT LINKING)
# -------------------------

class CrossReference(BaseModel):
    term: str
    linked_articles: List[str]


class CrossReferenceSection(BaseModel):
    references: List[CrossReference]


# -------------------------
# GLOSSARY COVERAGE ANALYSIS
# -------------------------

class CoverageGap(BaseModel):
    missing_term: str
    importance: Literal["low", "medium", "high"]
    suggestion: str


class CoverageAnalysis(BaseModel):
    coverage_score: Optional[float] = Field(ge=0, le=1)
    gaps: List[CoverageGap]


# -------------------------
# SEARCH OPTIMIZATION (AI + SEO ALIGNMENT)
# -------------------------

class SEOPlan(BaseModel):
    focus_keywords: List[str]
    semantic_keywords: List[str]
    search_variants: List[str]


# -------------------------
# SNIPPET OPTIMIZATION (AI OVERVIEW READY)
# -------------------------

class SnippetTarget(BaseModel):
    term: str
    definition: str
    format: Literal["definition", "table", "list"]


class SnippetSection(BaseModel):
    snippets: List[SnippetTarget]


# -------------------------
# AUTHORITY & TRUST SIGNALS
# -------------------------

class AuthoritySignals(BaseModel):
    expert_reviewed: Optional[bool] = False
    sources: Optional[List[str]]
    update_frequency: Optional[str]
    accuracy_level: Optional[Literal["high", "medium", "low"]]


# -------------------------
# USER EXPERIENCE DESIGN
# -------------------------

class UXOptimization(BaseModel):
    readability_level: Literal["simple", "moderate", "technical"]
    navigation_style: Optional[Literal["A-Z", "clustered", "searchable"]]
    search_enabled: Optional[bool] = True


# -------------------------
# INTERNAL LINKING (TOPICAL AUTHORITY ENGINE)
# -------------------------

class InternalLink(BaseModel):
    term: str
    anchor_text: str
    target_page: str


class InternalLinking(BaseModel):
    links: List[InternalLink]


# -------------------------
# SUMMARY LAYER
# -------------------------

class GlossarySummary(BaseModel):
    quick_overview: str
    key_takeaways: List[str]


# -------------------------
# FINAL GLOSSARY OUTLINE SCHEMA
# -------------------------

class GlossaryOutline(BaseModel):
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
        "Educational",
        "Technical",
        "Simplified",
        "Authoritative",
        "Informative"
    ]

    # Core structure
    hero: GlossaryHero
    domain_context: DomainContext

    # Glossary content system
    terms: List[GlossaryTerm]

    # Knowledge graph structure
    relationships: List[RelationshipMap]

    # Organizational system
    clusters: List[TermCluster]

    # Learning enhancement
    examples: ExampleSection
    misconceptions: MisconceptionsSection

    # SEO + AI optimization
    seo: SEOPlan
    snippets: SnippetSection

    # Coverage completeness
    coverage: CoverageAnalysis

    # Cross referencing system
    cross_references: CrossReferenceSection

    # Authority layer
    authority: AuthoritySignals

    # UX system
    ux: UXOptimization

    # Internal linking system
    internal_links: InternalLinking

    # Summary layer
    summary: GlossarySummary

    # Optimization Layer (2026 informational knowledge standard)
    content_goal: Literal[
        "define_domain_knowledge",
        "improve_understanding",
        "build_semantic_structure",
        "support_ai_search"
    ]

    success_metric: str = Field(
        default="User can understand and correctly use all key domain terms"
    )

    target_word_count: int = Field(
        default=1500,
        ge=600,
        le=6000,
        description="Glossaries scale with number of terms"
    )