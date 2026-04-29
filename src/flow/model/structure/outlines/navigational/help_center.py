# from typing import List, Optional
# from pydantic import Field
# from src.flow.model.structure.outlines.base import BaseOutline, Section


# class HelpCenterOutline(BaseOutline):
#     """Outline for a help center homepage or major category page."""
#     platform_name: str = Field(description="The platform providing help.")
#     top_categories: List[str] = Field(description="The main buckets of support (e.g., 'Billing', 'Account Setup').")
#     most_popular_articles: Optional[List[str]] = Field(description="Articles linked directly from the help center homepage.")
#     search_bar_prominence: bool = Field(default=True, description="Whether search is the primary action.")

from typing import List, Optional, Literal
from pydantic import BaseModel, Field


# -------------------------
# HERO / ENTRY EXPERIENCE
# -------------------------

class HelpCenterHero(BaseModel):
    headline: str = Field(description="Clear promise of self-service resolution")
    subheadline: str = Field(description="Explains what users can find and do")

    search_enabled: bool = True
    ai_assistant_enabled: bool = True

    quick_links: Optional[List[str]] = Field(
        default_factory=list,
        description="Most common help topics"
    )


# -------------------------
# SEARCH & DISCOVERY SYSTEM (CORE OF HELP CENTER)
# -------------------------

class SearchSystem(BaseModel):
    semantic_search: bool = True
    category_filtering: bool = True
    popular_searches: Optional[List[str]] = Field(default_factory=list)


# -------------------------
# HELP CATEGORIES (STRUCTURE OF KNOWLEDGE)
# -------------------------

class HelpArticle(BaseModel):
    title: str
    summary: Optional[str]
    link: str


class HelpCategory(BaseModel):
    name: str
    description: Optional[str]
    articles: List[HelpArticle]


class KnowledgeBase(BaseModel):
    categories: List[HelpCategory]


# -------------------------
# ISSUE → SOLUTION MODEL (VERY IMPORTANT IN 2026)
# -------------------------

class IssueSolution(BaseModel):
    issue: str
    cause: Optional[str]
    resolution_steps: List[str]


class TroubleshootingSection(BaseModel):
    common_issues: List[IssueSolution]


# -------------------------
# PRODUCT CONTEXT (MODERN HELP CENTERS ARE PRODUCT-AWARE)
# -------------------------

class ProductContext(BaseModel):
    product_name: str
    feature_links: Optional[List[str]] = Field(default_factory=list)
    version_specific_notes: Optional[List[str]] = Field(default_factory=list)


# -------------------------
# LEARNING PATHS (GUIDED SUPPORT FLOW)
# -------------------------

class LearningPath(BaseModel):
    name: str
    description: str
    steps: List[str]


class LearningPaths(BaseModel):
    paths: List[LearningPath]


# -------------------------
# SELF-SERVICE ACTIONS
# -------------------------

class SelfServiceAction(BaseModel):
    action_name: str
    description: str
    link: Optional[str]


class SelfServiceHub(BaseModel):
    actions: List[SelfServiceAction]


# -------------------------
# ESCALATION SYSTEM (WHEN HELP CENTER FAILS)
# -------------------------

class EscalationChannel(BaseModel):
    channel: Literal[
        "live_chat",
        "email_support",
        "ticket_system",
        "community_forum",
        "call_support"
    ]
    availability: Optional[str]
    response_time_sla: Optional[str]


class EscalationSystem(BaseModel):
    channels: List[EscalationChannel]


# -------------------------
# COMMUNITY SUPPORT (2026 STANDARD)
# -------------------------

class CommunitySupport(BaseModel):
    forum_link: Optional[str]
    top_discussions: Optional[List[str]] = Field(default_factory=list)
    contributors: Optional[List[str]] = Field(default_factory=list)


# -------------------------
# FEEDBACK LOOP (IMPROVEMENT SYSTEM)
# -------------------------

class FeedbackSystem(BaseModel):
    article_rating_enabled: bool = True
    feedback_form_enabled: bool = True
    improvement_tracking: Optional[bool] = True


# -------------------------
# CTA SYSTEM
# -------------------------

class CTASection(BaseModel):
    primary_cta: str
    secondary_cta: Optional[str] = None
    escalation_cta: Optional[str] = Field(
        default="Contact Support",
        description="Fallback if self-service fails"
    )


# -------------------------
# FINAL HELP CENTER SCHEMA
# -------------------------

class HelpCenterOutline(BaseModel):
    # Core metadata
    title: str
    slug_suggestion: str = Field(pattern=r"^[a-z0-9-]+$")
    focus_keyphrase: str

    target_audience: List[str]
    tone: Literal[
        "Helpful", "Clear", "Supportive",
        "Instructional", "Neutral", "Reassuring"
    ]

    # Entry experience
    hero: HelpCenterHero

    # Discovery system (core of Help Center)
    search: SearchSystem

    # Knowledge structure
    knowledge_base: KnowledgeBase

    # Product-aware help system
    product_context: Optional[ProductContext]

    # Issue-based resolution system
    troubleshooting: TroubleshootingSection

    # Guided learning
    learning_paths: LearningPaths

    # Self-service automation
    self_service: SelfServiceHub

    # Community layer
    community: Optional[CommunitySupport]

    # Escalation paths
    escalation: EscalationSystem

    # Feedback loop (continuous improvement)
    feedback: FeedbackSystem

    # CTA system
    cta: CTASection

    # Optimization Layer (2026 support intelligence standard)
    ai_support_assistant: bool = Field(
        default=True,
        description="AI-powered help bot for instant resolution"
    )

    deflection_goal: Optional[str] = Field(
        default="Reduce support tickets via self-service resolution"
    )

    target_time_to_resolution_seconds: Optional[int] = Field(
        default=180,
        description="Ideal time for user to find solution"
    )

    target_word_count: int = Field(
        default=1200,
        ge=500,
        le=5000,
        description="Help centers are large structured knowledge systems"
    )