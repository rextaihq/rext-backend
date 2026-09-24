# from typing import List, Optional, Literal
# from pydantic import BaseModel, Field, conlist


# class FAQItem(BaseModel):
#     """An individual question and answer pair."""
#     question: str = Field(description="The question to answer.")
#     answer_brief: str = Field(description="Brief, clear answer optimized for search snippets.")
#     detailed_answer: Optional[str] = Field(description="Detailed explanation if needed.")


# class FAQSection(BaseModel):
#     heading: str = Field(description="FAQ category (e.g., 'Pricing', 'Security').")
#     heading_level: Literal["H2", "H3"] = Field(description="Heading level.")
#     description: str = Field(description="Overview of the questions in this category.")
#     items: conlist(FAQItem, min_length=2, max_length=10)


# class FAQOutline(BaseModel):
#     title: str = Field(description="SEO-optimized FAQ title (e.g., '[Focus Keyphrase] FAQ').")
#     slug_suggestion: str = Field(
#         pattern=r"^[a-z0-9-]+$",
#         description="Suggested URL slug."
#     )
#     brief: str = Field(description="The primary objective and the audience for this FAQ.")

#     # Context
#     focus_keyphrase: str = Field(
#         description="The primary term, brand, or service the FAQ covers."
#     )
#     keywords_to_include: conlist(str, min_length=1)

#     # Structure
#     sections: conlist(FAQSection, min_length=1, max_length=10)

#     # Support Strategy
#     contact_instruction: Optional[str] = Field(description="How to reach out if someone has a question not in this FAQ.")

#     # Images Planning
#     image_suggestions: List[str] = Field(
#         description="Suggested icons or illustrations (min 1)."
#     )

#     # Links Planning
#     link_suggestions: List[str] = Field(
#         description="Suggested internal links (e.g., 'Contact Us', 'Documentation')."
#     )

#     # Schema
#     schema_type: Literal["FAQPage", "Article"] = Field(
#         default="FAQPage",
#         description="Primary schema.org type."
#     )

#     # Content Strategy
#     target_audience: List[str]
#     tone: Literal[
#     "Professional", "Conversational", "Authoritative", "Friendly",
#     "Encouraging", "Neutral", "Persuasive", "Analytical",
#     "Direct", "Action-oriented", "Trustworthy", "Urgent"
#     ]
#     target_word_count: int = Field(ge=500, le=3000)


from typing import List, Literal, Optional

from pydantic import BaseModel, Field

# -------------------------
# HERO / FAQ POSITIONING
# -------------------------


class FAQHero(BaseModel):
    headline: str = Field(description="Main FAQ page title (question-driven or topic-driven)")
    subheadline: str = Field(description="Clarifies what users will learn")

    intent_summary: str = Field(description="What problem these FAQs solve for users")


# -------------------------
# QUESTION INTENT CLASSIFICATION (CRITICAL IN 2026)
# -------------------------


class QuestionIntent(BaseModel):
    intent_type: Literal[
        "definition",
        "how_to",
        "troubleshooting",
        "comparison",
        "pricing",
        "feature",
        "policy",
        "general_knowledge",
    ]
    user_goal: str


# -------------------------
# ANSWER STRUCTURE (SNIPPET-OPTIMIZED)
# -------------------------


class AnswerStructure(BaseModel):
    short_answer: str = Field(description="1–2 sentence direct answer (snippet-ready)")
    detailed_explanation: Optional[str]
    key_points: Optional[List[str]]


# -------------------------
# FAQ ITEM (CORE UNIT)
# -------------------------


class FAQItem(BaseModel):
    question: str
    intent: QuestionIntent

    answer: AnswerStructure

    difficulty_level: Literal["basic", "intermediate", "advanced"]

    related_keywords: Optional[List[str]]


# -------------------------
# FAQ CLUSTERING (TOPIC ORGANIZATION)
# -------------------------


class FAQCluster(BaseModel):
    cluster_name: str
    description: Optional[str]
    questions: List[FAQItem]


# -------------------------
# COVERAGE ANALYSIS (2026 SEO REQUIREMENT)
# -------------------------


class CoverageGap(BaseModel):
    missing_area: str
    importance: Literal["low", "medium", "high"]
    suggestion: str


class CoverageAnalysis(BaseModel):
    coverage_score: Optional[float] = Field(ge=0, le=1)
    gaps: List[CoverageGap]


# -------------------------
# FEATURED SNIPPET TARGETING (AI SEARCH OPTIMIZATION)
# -------------------------


class SnippetTarget(BaseModel):
    question: str
    answer_format: Literal["definition", "list", "steps", "table"]
    optimized_answer: str


class SnippetSection(BaseModel):
    snippets: List[SnippetTarget]


# -------------------------
# RELATED QUESTIONS (QUERY EXPANSION SYSTEM)
# -------------------------


class RelatedQuestion(BaseModel):
    question: str
    reason: str


class RelatedQuestions(BaseModel):
    items: List[RelatedQuestion]


# -------------------------
# AUTHORITY & TRUST SIGNALS
# -------------------------


class AuthoritySignals(BaseModel):
    expert_reviewed: Optional[bool] = False
    data_sources: Optional[List[str]]
    update_frequency: Optional[str]
    accuracy_level: Optional[Literal["high", "medium", "low"]]


# -------------------------
# USER EXPERIENCE OPTIMIZATION
# -------------------------


class UXOptimization(BaseModel):
    readability_level: Literal["simple", "moderate", "technical"]
    avg_answer_length: Optional[str]
    scan_friendly_format: Optional[bool] = True


# -------------------------
# INTERNAL LINKING (TOPICAL AUTHORITY)
# -------------------------


class InternalLink(BaseModel):
    anchor_text: str
    target_page: str
    purpose: Optional[str]


class InternalLinking(BaseModel):
    links: List[InternalLink]


# -------------------------
# FAQ SUMMARY (AI + SNIPPET LAYER)
# -------------------------


class FAQSummary(BaseModel):
    quick_summary: str
    key_takeaways: List[str]


# -------------------------
# FINAL FAQ OUTLINE SCHEMA
# -------------------------


class FAQOutline(BaseModel):
    # Core metadata
    title: str
    slug_suggestion: str = Field(pattern=r"^[a-z0-9-]+$")
    focus_keyphrase: str
    keywords_to_include: List[str] = Field(
        default_factory=list,
        description="Secondary and long-tail keywords to naturally incorporate throughout the page.",
    )

    target_audience: List[str]
    tone: Literal["Informative", "Helpful", "Clear", "Supportive", "Neutral", "Educational"]

    # Core structure
    hero: FAQHero

    # Question system
    clusters: List[FAQCluster]

    # Snippet optimization (AI search critical)
    snippets: SnippetSection

    # Related question expansion
    related_questions: RelatedQuestions

    # Coverage completeness analysis
    coverage: CoverageAnalysis

    # Authority layer
    authority: AuthoritySignals

    # UX optimization layer
    ux: UXOptimization

    # Internal linking system
    internal_links: InternalLinking

    # Summary layer (AI + human readability)
    summary: FAQSummary

    # Optimization Layer (2026 informational SEO standard)
    content_goal: Literal[
        "answer_user_questions",
        "improve_search_visibility",
        "reduce_support_queries",
        "build_topic_coverage",
    ]

    success_metric: str = Field(
        default="User finds accurate answer without needing external search"
    )

    target_word_count: int = Field(
        default=1200, ge=500, le=4000, description="Depends on number of questions and depth"
    )
