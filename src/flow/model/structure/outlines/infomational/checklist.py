# from typing import List, Optional, Literal
# from pydantic import BaseModel, Field, conlist


# class ChecklistItem(BaseModel):
#     """An individual actionable item in the checklist."""
#     label: str = Field(description="The checklist item text.")
#     context: Optional[str] = Field(description="Brief explanation of why this item is necessary.")
#     difficulty: Literal["Easy", "Medium", "Hard"] = "Easy"


# class ChecklistSection(BaseModel):
#     heading: str = Field(description="Section heading (e.g., 'Phase 1', 'Preparation').")
#     heading_level: Literal["H2", "H3"] = Field(description="Heading level.")
#     description: str = Field(description="Overview of this checklist phase.")
#     items: conlist(ChecklistItem, min_length=2, max_length=15)


# class ChecklistOutline(BaseModel):
#     title: str = Field(description="SEO-optimized checklist title starting with the focus keyphrase.")
#     slug_suggestion: str = Field(
#         pattern=r"^[a-z0-9-]+$",
#         description="Suggested URL slug."
#     )
#     brief: str = Field(description="Main objective and the specific process the checklist covers.")

#     # Context
#     focus_keyphrase: str = Field(
#         description="The primary action/process the checklist follows."
#     )
#     keywords_to_include: conlist(str, min_length=2)

#     # Structure
#     sections: conlist(ChecklistSection, min_length=2, max_length=10)

#     # Checklist Value Proposition
#     total_items: Optional[int] = Field(description="Total number of checklist items in the complete article.")
#     estimated_time: Optional[str] = Field(description="Total estimated time to complete all items.")

#     # Images/Icons Planning
#     image_suggestions: List[str] = Field(
#         description="Suggested header image or specific icons for phases."
#     )

#     # Links Planning
#     link_suggestions: List[str] = Field(
#         description="Suggested internal and outbound links."
#     )

#     # Schema
#     schema_type: Literal["Article", "HowTo"] = Field(
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
#     target_word_count: int = Field(ge=500, le=3000)


from typing import List, Literal, Optional

from pydantic import BaseModel, Field

# -------------------------
# HERO / PURPOSE DEFINITION
# -------------------------


class ChecklistHero(BaseModel):
    headline: str = Field(
        description="Clear task outcome title (e.g., 'Complete SEO Audit Checklist')"
    )
    subheadline: str = Field(description="Explains what the checklist helps achieve")

    success_outcome: str = Field(
        description="Final result user achieves after completing checklist"
    )


# -------------------------
# CHECKLIST INTENT (CRITICAL IN 2026 STRUCTURED CONTENT)
# -------------------------


class ChecklistIntent(BaseModel):
    goal_type: Literal["completion", "optimization", "setup", "audit", "validation", "execution"]
    user_goal: List[str]
    complexity_level: Literal["basic", "intermediate", "advanced"]


# -------------------------
# TASK ITEM (CORE STRUCTURE)
# -------------------------


class ChecklistItem(BaseModel):
    task: str
    description: Optional[str]

    importance: Literal["low", "medium", "high"]
    required: bool = True

    expected_result: Optional[str]
    validation_criteria: Optional[str]


# -------------------------
# CHECKLIST PHASE (WORKFLOW GROUPING)
# -------------------------


class ChecklistPhase(BaseModel):
    phase_name: str
    description: Optional[str]
    items: List[ChecklistItem]


# -------------------------
# DEPENDENCY MAPPING (2026 STRUCTURED WORKFLOWS)
# -------------------------


class TaskDependency(BaseModel):
    task: str
    depends_on: List[str]


class DependencyGraph(BaseModel):
    dependencies: List[TaskDependency]


# -------------------------
# VALIDATION SYSTEM (QUALITY CONTROL LAYER)
# -------------------------


class ValidationRule(BaseModel):
    rule: str
    purpose: str
    how_to_verify: str


class ValidationSection(BaseModel):
    rules: List[ValidationRule]


# -------------------------
# OUTCOME TRACKING (WHY EACH TASK EXISTS)
# -------------------------


class OutcomeMapping(BaseModel):
    task: str
    outcome: str


class OutcomeSection(BaseModel):
    mappings: List[OutcomeMapping]


# -------------------------
# COMMON MISTAKES (CRITICAL FOR CHECKLISTS)
# -------------------------


class Mistake(BaseModel):
    mistake: str
    consequence: str
    prevention: str


class MistakesSection(BaseModel):
    mistakes: List[Mistake]


# -------------------------
# PRIORITY SYSTEM
# -------------------------


class PriorityGuide(BaseModel):
    high_priority_tasks: List[str]
    medium_priority_tasks: List[str]
    low_priority_tasks: List[str]


# -------------------------
# ESTIMATED EFFORT MODEL
# -------------------------


class EffortEstimate(BaseModel):
    total_time: Optional[str]
    per_phase_time: Optional[List[str]]
    difficulty_rating: Literal["easy", "moderate", "hard"]


# -------------------------
# TOOL / RESOURCE SUPPORT
# -------------------------


class Resource(BaseModel):
    name: str
    purpose: str
    link: Optional[str]


class ResourcesSection(BaseModel):
    resources: List[Resource]


# -------------------------
# PROGRESS TRACKING SYSTEM
# -------------------------


class ProgressTracker(BaseModel):
    completion_percentage_stages: List[str]
    milestones: List[str]


# -------------------------
# FAQ (CHECKLIST-SPECIFIC QUESTIONS)
# -------------------------


class FAQItem(BaseModel):
    question: str
    answer: str


class FAQSection(BaseModel):
    faqs: List[FAQItem]


# -------------------------
# FINAL CHECKLIST SCHEMA
# -------------------------


class ChecklistOutline(BaseModel):
    # Core metadata
    title: str
    slug_suggestion: str = Field(pattern=r"^[a-z0-9-]+$")
    focus_keyphrase: str
    keywords_to_include: List[str] = Field(
        default_factory=list,
        description="Secondary and long-tail keywords to naturally incorporate throughout the page.",
    )

    target_audience: List[str]
    tone: Literal["Instructional", "Practical", "Structured", "Action-oriented", "Guided"]

    # Core intent system
    hero: ChecklistHero
    intent: ChecklistIntent

    # Structured workflow
    phases: List[ChecklistPhase]

    # Dependency logic (advanced workflows)
    dependencies: Optional[DependencyGraph]

    # Outcome mapping (critical for meaning clarity)
    outcomes: OutcomeSection

    # Validation system (quality assurance)
    validation: ValidationSection

    # Priority system
    priority: PriorityGuide

    # Progress tracking
    progress: ProgressTracker

    # Mistake prevention
    mistakes: MistakesSection

    # Resource support
    resources: Optional[ResourcesSection]

    # Effort estimation
    effort: EffortEstimate

    # FAQ layer (AEO / PAA coverage for checklist-specific questions)
    faqs: FAQSection

    # Optimization Layer (2026 informational execution standard)
    completion_goal: Literal[
        "task_completion",
        "workflow_execution",
        "audit_completion",
        "setup_completion",
        "optimization_completion",
    ]

    success_definition: str = Field(
        default="User successfully completes all required tasks with validation passed"
    )

    target_completion_time_minutes: Optional[int] = Field(
        default=30, description="Ideal time to complete checklist workflow"
    )

    target_word_count: int = Field(
        default=900, ge=400, le=3000, description="Checklists are concise execution systems"
    )
