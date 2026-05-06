# from typing import List, Optional, Literal
# from pydantic import BaseModel, Field, conlist


# class Resource(BaseModel):
#     """A specific tool, link, or resource."""
#     title: str = Field(description="Name or title of the resource.")
#     url: Optional[str] = Field(description="URL to the resource (if applicable).")
#     description: str = Field(description="Brief overview of what the resource provides.")
#     category: Optional[str] = Field(description="Sub-category within this section (e.g., 'Free', 'Premium').")
#     pros: Optional[List[str]] = Field(default_factory=list, description="Key benefits or advantages.")


# class ResourceSection(BaseModel):
#     heading: str = Field(description="Category heading (e.g., 'Monitoring Tools', 'Research Sources').")
#     heading_level: Literal["H2", "H3"] = Field(description="Heading level.")
#     description: str = Field(description="Brief overview of the resources in this section.")
#     resources: conlist(Resource, min_length=2, max_length=15)


# class ResourceListOutline(BaseModel):
#     title: str = Field(description="SEO-optimized resource list title starting with focus keyphrase.")
#     slug_suggestion: str = Field(
#         pattern=r"^[a-z0-9-]+$",
#         description="Suggested URL slug."
#     )
#     brief: str = Field(description="Goal of this curated list and the audience it serves.")
    
#     # Selection Criteria Strategy
#     focus_keyphrase: str = Field(
#         description="The primary domain or skill the resources support."
#     )
#     keywords_to_include: conlist(str, min_length=2)
#     selection_criteria: str = Field(description="How these resources were chosen.")
    
#     # Structure
#     sections: conlist(ResourceSection, min_length=3, max_length=10)
    
#     # Images/Graphics Planning
#     image_suggestions: List[str] = Field(
#         description="Suggested header image or specific graphics for sections (min 1)."
#     )
    
#     # Links Planning
#     link_suggestions: List[str] = Field(
#         description="Direct links to resources and internal related content."
#     )
    
#     # Schema
#     schema_type: Literal["ItemList", "Article", "WebPage"] = Field(
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
#     target_word_count: int = Field(ge=500, le=4000)



from typing import List, Optional, Literal
from pydantic import BaseModel, Field


# -------------------------
# HERO / CURATION POSITIONING
# -------------------------

class ResourceHero(BaseModel):
    headline: str = Field(description="Clear value-driven title (e.g., 'Best Resources to Learn X in 2026')")
    subheadline: str = Field(description="What users will achieve using this list")

    curation_purpose: str = Field(
        description="Why this resource list exists and what gap it fills"
    )


# -------------------------
# LEARNING CONTEXT (VERY IMPORTANT IN 2026 CURATION SYSTEMS)
# -------------------------

class LearningContext(BaseModel):
    skill_level: Literal["beginner", "intermediate", "advanced"]
    learning_goal: List[str]
    estimated_time_to_value: Optional[str]


# -------------------------
# RESOURCE ENTITY (CORE UNIT)
# -------------------------

class ResourceItem(BaseModel):
    name: str
    description: str

    resource_type: Literal[
        "article",
        "documentation",
        "video",
        "course",
        "tool",
        "research_paper",
        "ebook",
        "community",
        "github_repo"
    ]

    url: Optional[str]

    difficulty_level: Literal["beginner", "intermediate", "advanced"]

    credibility_score: Optional[Literal["high", "medium", "low"]]

    why_its_useful: str

    key_takeaways: Optional[List[str]]


# -------------------------
# RESOURCE CATEGORY (STRUCTURED GROUPING)
# -------------------------

class ResourceCategory(BaseModel):
    category_name: str
    purpose: str
    resources: List[ResourceItem]


# -------------------------
# LEARNING PATH (SEQUENCED KNOWLEDGE FLOW)
# -------------------------

class LearningStep(BaseModel):
    step_order: int
    goal: str
    recommended_resources: List[str]


class LearningPath(BaseModel):
    steps: List[LearningStep]


# -------------------------
# QUALITY SIGNALS (2026 TRUST REQUIREMENT)
# -------------------------

class QualitySignals(BaseModel):
    expert_curated: Optional[bool] = True
    updated_recently: Optional[bool]
    source_reliability_notes: Optional[List[str]]


# -------------------------
# RESOURCE COMPARISON (WHEN MULTIPLE OPTIONS EXIST)
# -------------------------

class ResourceComparison(BaseModel):
    resource_a: str
    resource_b: str
    difference_summary: str
    best_for: str


# -------------------------
# USE CASE MAPPING (CRITICAL FOR MODERN CURATION)
# -------------------------

class UseCase(BaseModel):
    scenario: str
    best_resources: List[str]


class UseCaseSection(BaseModel):
    use_cases: List[UseCase]


# -------------------------
# TAGGING SYSTEM (SEO + AI RETRIEVAL)
# -------------------------

class TaggingSystem(BaseModel):
    topics: List[str]
    keywords: List[str]
    semantic_tags: List[str]


# -------------------------
# RESOURCE SUMMARY (SNIPPET + AI ANSWERS)
# -------------------------

class ResourceSummary(BaseModel):
    quick_overview: str
    top_picks: List[str]


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
# FINAL RESOURCE LIST SCHEMA
# -------------------------

class ResourceListOutline(BaseModel):
    # Core metadata
    title: str
    slug_suggestion: str = Field(pattern=r"^[a-z0-9-]+$")
    focus_keyphrase: str

    target_audience: List[str]
    tone: Literal[
        "Curated",
        "Educational",
        "Informative",
        "Guided",
        "Practical"
    ]

    # Core structure
    hero: ResourceHero
    learning_context: LearningContext

    # Resource system
    categories: List[ResourceCategory]

    # Learning progression system
    learning_path: Optional[LearningPath]

    # Quality control layer
    quality: QualitySignals

    # Use-case mapping system
    use_cases: UseCaseSection

    # Comparison system (optional but powerful)
    comparisons: Optional[List[ResourceComparison]]

    # Tagging system (SEO + AI optimization)
    tagging: TaggingSystem

    # Internal linking system
    internal_links: InternalLinking

    # Summary layer
    summary: ResourceSummary

    # Optimization Layer (2026 informational curation standard)
    content_goal: Literal[
        "provide_best_resources",
        "accelerate_learning",
        "reduce_information_overload",
        "curate_trusted_sources"
    ]

    success_metric: str = Field(
        default="User finds the best trusted resources without searching externally"
    )

    target_word_count: int = Field(
        default=1200,
        ge=500,
        le=5000,
        description="Resource pages scale with number of items"
    )