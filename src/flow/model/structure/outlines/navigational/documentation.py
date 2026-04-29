# from typing import List, Optional
# from pydantic import Field
# from src.flow.model.structure.outlines.base import BaseOutline, Section


# class DocumentationOutline(BaseOutline):
#     """Outline for technical documentation or user manuals."""
#     topic_or_module: str = Field(description="The specific topic or module being documented.")
#     intended_audience_technical_level: str = Field(description="e.g., 'Beginner', 'Advanced Developer'.")
#     prerequisites_needed: Optional[List[str]] = Field(description="What the user must know or have before proceeding.")
#     includes_code_snippets: bool = Field(default=False, description="Whether code blocks are required in the documentation.")

from typing import List, Optional, Literal
from pydantic import BaseModel, Field


# -------------------------
# HERO / ENTRY POINT
# -------------------------

class DocumentationHero(BaseModel):
    title: str = Field(description="Product or docs title")
    subheadline: str = Field(description="What the documentation helps users achieve")

    search_enabled: bool = True
    quick_start_cta: Optional[str] = Field(
        default="Get Started",
        description="Primary entry point for new users"
    )


# -------------------------
# NAVIGATION STRUCTURE (CRITICAL)
# -------------------------

class DocSection(BaseModel):
    title: str
    description: Optional[str]
    link: str


class NavigationTree(BaseModel):
    getting_started: List[DocSection]
    guides: List[DocSection]
    api_reference: List[DocSection]
    sdk_docs: Optional[List[DocSection]] = Field(default_factory=list)
    tutorials: Optional[List[DocSection]] = Field(default_factory=list)
    faq: Optional[List[DocSection]] = Field(default_factory=list)


# -------------------------
# LEARNING PATHS (MODERN UX)
# -------------------------

class LearningPath(BaseModel):
    name: str
    description: str
    steps: List[str]


class LearningPaths(BaseModel):
    paths: List[LearningPath]


# -------------------------
# API / TECHNICAL REFERENCE
# -------------------------

class APIParameter(BaseModel):
    name: str
    type: str
    required: bool
    description: str


class APIEndpoint(BaseModel):
    method: Literal["GET", "POST", "PUT", "DELETE", "PATCH"]
    endpoint: str
    description: str
    parameters: List[APIParameter]
    example_request: Optional[str]
    example_response: Optional[str]


class APIReference(BaseModel):
    version: str
    base_url: str
    endpoints: List[APIEndpoint]


# -------------------------
# CODE EXAMPLES (CRITICAL FOR DEVS)
# -------------------------

class CodeExample(BaseModel):
    language: Literal[
        "python", "javascript", "typescript", "java",
        "go", "ruby", "curl", "php"
    ]
    code: str
    description: Optional[str]


# -------------------------
# GUIDES (TASK-BASED LEARNING)
# -------------------------

class Guide(BaseModel):
    title: str
    difficulty: Literal["beginner", "intermediate", "advanced"]
    steps: List[str]
    code_examples: Optional[List[CodeExample]] = Field(default_factory=list)


# -------------------------
# TROUBLESHOOTING (VERY IMPORTANT IN 2026)
# -------------------------

class TroubleshootingItem(BaseModel):
    issue: str
    cause: str
    solution: str


class TroubleshootingSection(BaseModel):
    common_issues: List[TroubleshootingItem]


# -------------------------
# VERSIONING SYSTEM (CRITICAL FOR APIS)
# -------------------------

class VersionInfo(BaseModel):
    version: str
    release_date: Optional[str]
    breaking_changes: Optional[List[str]]
    migration_guide: Optional[str]


# -------------------------
# SEARCH + DISCOVERY SYSTEM
# -------------------------

class SearchSystem(BaseModel):
    enabled: bool = True
    indexing_scope: List[str] = Field(
        description="Sections included in search (API, guides, etc.)"
    )
    semantic_search_enabled: bool = True


# -------------------------
# CONTRIBUTION / EXTENSIBILITY
# -------------------------

class ContributionGuide(BaseModel):
    github_repo: Optional[str]
    contribution_steps: List[str]
    coding_standards: Optional[List[str]]


# -------------------------
# CTA (DEVELOPER ACTIONS)
# -------------------------

class CTASection(BaseModel):
    primary_cta: str
    secondary_cta: Optional[str] = None
    support_cta: Optional[str] = Field(
        default="Contact Support",
        description="Fallback for unresolved issues"
    )


# -------------------------
# FINAL DOCUMENTATION PAGE SCHEMA
# -------------------------

class DocumentationOutline(BaseModel):
    # Core metadata
    title: str
    slug_suggestion: str = Field(pattern=r"^[a-z0-9-]+$")
    focus_keyphrase: str

    target_audience: List[str]
    tone: Literal[
        "Technical", "Clear", "Educational",
        "Neutral", "Professional", "Instructional"
    ]

    # Entry experience
    hero: DocumentationHero

    # Navigation system (core of docs)
    navigation: NavigationTree

    # Learning system
    learning_paths: LearningPaths

    # Technical reference
    api_reference: Optional[APIReference]

    # Guides + tutorials
    guides: List[Guide]

    # Code examples
    code_examples: Optional[List[CodeExample]]

    # Debugging support
    troubleshooting: TroubleshootingSection

    # Versioning (very important in modern systems)
    versioning: Optional[List[VersionInfo]]

    # Search system
    search: SearchSystem

    # Contribution system
    contribution: Optional[ContributionGuide]

    # CTA (developer actions)
    cta: CTASection

    # Optimization Layer (2026 dev experience standard)
    interactive_docs_enabled: bool = Field(
        default=True,
        description="Live API testing / playground support"
    )

    ai_assistant_enabled: bool = Field(
        default=True,
        description="AI-powered doc search and explanation layer"
    )

    target_time_to_first_success_seconds: Optional[int] = Field(
        default=300,
        description="Time for developer to complete first successful integration"
    )

    target_word_count: int = Field(
        default=1200,
        ge=500,
        le=5000,
        description="Docs are medium-to-large structured knowledge systems"
    )