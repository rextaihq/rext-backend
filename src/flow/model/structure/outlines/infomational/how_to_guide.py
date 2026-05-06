# from typing import List, Optional, Literal
# from pydantic import BaseModel, Field, conlist


# class ImageSuggestion(BaseModel):
#     """Suggested image for a section with SEO context."""
    
#     description: str = Field(
#         description="Description of what the image should show."
#     )
#     alt_text_template: str = Field(
#         description="Template for SEO-optimized alt text (should include keyphrase or synonyms)."
#     )
#     section: str = Field(
#         description="Which section this image belongs to (e.g., 'introduction', 'step-1')."
#     )


# class LinkSuggestion(BaseModel):
#     """Suggested link with context."""
    
#     anchor_text: str = Field(description="Suggested anchor text.")
#     link_type: Literal["internal", "outbound"] = Field(
#         description="Type of link to suggest."
#     )
#     context: str = Field(
#         description="Context about what this link should point to or why it's needed."
#     )
#     section: str = Field(
#         description="Which section this link should appear in."
#     )


# class Fact(BaseModel):
#     """Verifiable fact or statistic with source citation context."""
    
#     text: str = Field(description="The factual statement or statistic.")


# class Step(BaseModel):
#     """A single actionable step in the guide."""
#     title: str = Field(description="Title of the step.")
#     description: str = Field(description="Detailed instructions for this step.")
#     tools_needed: Optional[List[str]] = Field(default_factory=list, description="Specific tools or materials for this step.")


# class HowToSection(BaseModel):
#     heading: str = Field(description="Section heading text.")
#     heading_level: Literal["H2", "H3"] = Field(description="Heading level.")
#     description: str = Field(description="What this section will cover.")
#     key_points: conlist(str, min_length=2, max_length=6)
#     steps: Optional[List[Step]] = Field(default_factory=list, description="Instructional steps within this section.")


# class HowToGuideOutline(BaseModel):
#     title: str = Field(description="SEO-optimized guide title starting with the focus keyphrase.")
#     slug_suggestion: str = Field(
#         pattern=r"^[a-z0-9-]+$",
#         description="Suggested URL slug containing the focus keyphrase."
#     )
#     brief: str = Field(description="Guide goal and the specific problem it solves.")
    
#     # Keyphrase Strategy
#     focus_keyphrase: str = Field(
#         description="The primary focus keyphrase for this guide."
#     )
#     keywords_to_include: conlist(str, min_length=1)
    
#     # Prerequisite Info
#     total_time: Optional[str] = Field(description="Estimated time to complete (e.g., '30 mins').")
#     difficulty: Literal["Beginner", "Intermediate", "Advanced"] = "Beginner"
#     tools_needed: List[str] = Field(default_factory=list, description="Overall tools or supplies required.")
    
#     # Structure
#     sections: conlist(HowToSection, min_length=3, max_length=10)
#     faqs: Optional[List[str]] = Field(default_factory=list, description="FAQ questions for schema.")
    
#     # Images Planning
#     image_suggestions: List[ImageSuggestion] = Field(
#         min_length=1,
#         description="Suggested images (min 1)."
#     )
    
#     # Links Planning
#     link_suggestions: List[LinkSuggestion] = Field(
#         min_length=2,
#         description="Suggested internal and outbound links (min 2)."
#     )
    
#     # Schema
#     schema_type: Literal["HowTo", "Article"] = Field(
#         default="HowTo",
#         description="Primary schema.org type."
#     )
    
#     # Content Strategy
#     target_audience: List[str]
#     tone: Literal[
#     "Professional", "Conversational", "Authoritative", "Friendly", 
#     "Encouraging", "Neutral", "Persuasive", "Analytical", 
#     "Direct", "Action-oriented", "Trustworthy", "Urgent"
#     ]
#     target_word_count: int = Field(ge=800, le=5000)



from typing import List, Optional, Literal
from pydantic import BaseModel, Field


# -------------------------
# HERO / GOAL DEFINITION
# -------------------------

class HowToHero(BaseModel):
    headline: str = Field(description="Clear action-driven title (e.g., 'How to set up X in 10 minutes')")
    subheadline: str = Field(description="What user will achieve after completion")

    final_outcome: str = Field(
        description="Clear definition of success state after completing the guide"
    )


# -------------------------
# USER CONTEXT (VERY IMPORTANT IN 2026 GUIDES)
# -------------------------

class UserContext(BaseModel):
    skill_level: Literal["beginner", "intermediate", "advanced"]
    prerequisites_assumed: List[str]
    estimated_time: str


# -------------------------
# PREREQUISITES (FAILURE PREVENTION LAYER)
# -------------------------

class Prerequisite(BaseModel):
    item: str
    required: bool
    purpose: Optional[str]


class PrerequisitesSection(BaseModel):
    items: List[Prerequisite]


# -------------------------
# STEP STRUCTURE (CORE EXECUTION ENGINE)
# -------------------------

class Step(BaseModel):
    step_number: int
    title: str
    description: str

    expected_result: Optional[str]

    warning: Optional[str]
    tips: Optional[List[str]]


class StepSection(BaseModel):
    steps: List[Step]


# -------------------------
# BRANCHING LOGIC (2026 REAL-WORLD GUIDES REQUIRE THIS)
# -------------------------

class ConditionalPath(BaseModel):
    condition: str
    next_steps: List[int]
    explanation: str


class BranchingLogic(BaseModel):
    conditions: List[ConditionalPath]


# -------------------------
# TOOLS & RESOURCES (EXECUTION SUPPORT)
# -------------------------

class Tool(BaseModel):
    name: str
    purpose: str
    optional: bool


class ToolsSection(BaseModel):
    tools: List[Tool]


# -------------------------
# COMMON ERRORS (FAILURE PREVENTION SYSTEM)
# -------------------------

class CommonError(BaseModel):
    mistake: str
    consequence: str
    solution: str


class ErrorPreventionSection(BaseModel):
    errors: List[CommonError]


# -------------------------
# VALIDATION / SUCCESS CHECKS
# -------------------------

class ValidationStep(BaseModel):
    check: str
    expected_result: str


class ValidationSection(BaseModel):
    checks: List[ValidationStep]


# -------------------------
# VARIATIONS (REAL-WORLD ADAPTATION LAYER)
# -------------------------

class Variation(BaseModel):
    scenario: str
    adjustment: str


class VariationsSection(BaseModel):
    variations: List[Variation]


# -------------------------
# TIME & EFFORT MODEL
# -------------------------

class EffortEstimate(BaseModel):
    total_time: str
    difficulty: Literal["easy", "moderate", "hard"]


# -------------------------
# SAFETY / RISK NOTES
# -------------------------

class SafetyNote(BaseModel):
    risk: str
    mitigation: str


class SafetySection(BaseModel):
    notes: List[SafetyNote]


# -------------------------
# SUMMARY LAYER (AI + SNIPPET OPTIMIZED)
# -------------------------

class Summary(BaseModel):
    quick_summary: str
    key_takeaways: List[str]


# -------------------------
# FAQ (GUIDE-SPECIFIC QUESTIONS)
# -------------------------

class FAQItem(BaseModel):
    question: str
    answer: str


class FAQSection(BaseModel):
    faqs: List[FAQItem]


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
# FINAL HOW-TO GUIDE SCHEMA
# -------------------------

class HowToGuideOutline(BaseModel):
    # Core metadata
    title: str
    slug_suggestion: str = Field(pattern=r"^[a-z0-9-]+$")
    focus_keyphrase: str

    target_audience: List[str]
    tone: Literal[
        "Instructional",
        "Practical",
        "Guided",
        "Clear",
        "Action-oriented"
    ]

    # Core structure
    hero: HowToHero
    user_context: UserContext
    prerequisites: PrerequisitesSection

    # Execution engine
    steps: StepSection
    branching: Optional[BranchingLogic]

    # Support systems
    tools: ToolsSection

    # Failure prevention system
    error_prevention: ErrorPreventionSection
    safety: Optional[SafetySection]

    # Validation system
    validation: ValidationSection

    # Adaptation layer
    variations: VariationsSection

    # Outcome quality layer
    effort: EffortEstimate

    # FAQ layer
    faqs: FAQSection

    # Internal linking
    internal_links: InternalLinking

    # Summary layer
    summary: Summary

    # Optimization Layer (2026 informational execution standard)
    content_goal: Literal[
        "help_user_complete_task",
        "reduce_execution_failure",
        "guide_step_by_step_action",
        "ensure_success_outcome"
    ]

    success_definition: str = Field(
        default="User successfully completes task with validated result"
    )

    target_completion_time_minutes: Optional[int] = Field(
        default=15,
        description="Optimal time to complete task"
    )

    target_word_count: int = Field(
        default=2000,
        ge=1500,
        le=3000,
        description="Depends on complexity of task"
    )