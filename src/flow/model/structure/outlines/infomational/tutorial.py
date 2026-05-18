# from typing import List, Optional, Literal
# from pydantic import BaseModel, Field, conlist


# class CodeSnippet(BaseModel):
#     """A suggested code block or mathematical equation/expression."""
#     language: str = Field(description="Programming language or format (e.g., 'python', 'json', 'latex').")
#     description: str = Field(description="Explanation of what this snippet does or teaches.")
#     difficulty: Literal["Easy", "Medium", "Hard"] = "Easy"


# class TutorialStep(BaseModel):
#     """A practical step within the tutorial."""
#     title: str = Field(description="Tutorial step heading.")
#     description: str = Field(description="Practical instructions for the user.")
#     code_suggestions: Optional[List[CodeSnippet]] = Field(default_factory=list, description="Associated code snippets or technical diagrams.")


# class TutorialSection(BaseModel):
#     heading: str = Field(description="Section heading.")
#     heading_level: Literal["H2", "H3"] = Field(description="Heading level.")
#     description: str = Field(description="Goal of this section in the learning curve.")
#     steps: conlist(TutorialStep, min_length=1, max_length=10)


# class TutorialOutline(BaseModel):
#     title: str = Field(description="SEO-optimized tutorial title starting with 'How to' or including focus keyphrase.")
#     slug_suggestion: str = Field(
#         pattern=r"^[a-z0-9-]+$",
#         description="Suggested URL slug."
#     )
#     brief: str = Field(description="The primary learning objective and prerequisite knowledge.")
    
#     # Prerequisite Strategy
#     focus_keyphrase: str = Field(
#         description="The primary technical skill or concept being taught."
#     )
#     keywords_to_include: conlist(str, min_length=2)
#     difficulty: Literal["Beginner", "Intermediate", "Advanced"] = "Beginner"
#     environment_setup: Optional[str] = Field(description="Necessary tools, software, or credentials.")
    
#     # Structure
#     sections: conlist(TutorialSection, min_length=3, max_length=10)
    
#     # Images/Diagrams Planning
#     image_suggestions: List[str] = Field(
#         description="Suggested screenshots or technical diagrams (min 2)."
#     )
    
#     # Links Planning
#     link_suggestions: List[str] = Field(
#         description="Related documentation or prerequisites."
#     )
    
#     # Schema
#     schema_type: Literal["HowTo", "TechArticle", "Article"] = Field(
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
# HERO / LEARNING OUTCOME
# -------------------------

class TutorialHero(BaseModel):
    headline: str = Field(description="Skill-focused title (e.g., 'How to Build X from Scratch')")
    subheadline: str = Field(description="What skill the user will gain")

    final_skill_outcome: str = Field(
        description="Clear statement of what the user can do after completing tutorial"
    )


# -------------------------
# SKILL CONTEXT (CORE IN 2026 EDUCATIONAL SYSTEMS)
# -------------------------

class SkillContext(BaseModel):
    skill_type: Literal[
        "technical",
        "creative",
        "analytical",
        "operational"
    ]
    difficulty_level: Literal["beginner", "intermediate", "advanced"]
    estimated_time_to_master: Optional[str]


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
# MODULE STRUCTURE (MODERN TUTORIAL DESIGN)
# -------------------------

class PracticeTask(BaseModel):
    task: str
    expected_result: str


class Module(BaseModel):
    module_name: str
    learning_objective: str

    explanation: str

    practice_tasks: List[PracticeTask]

    checkpoint: Optional[str]


class ModuleSection(BaseModel):
    modules: List[Module]


# -------------------------
# STEP BREAKDOWN (WITHIN MODULES IF NEEDED)
# -------------------------

class Step(BaseModel):
    step: str
    description: str
    expected_output: Optional[str]


class StepSection(BaseModel):
    steps: List[Step]


# -------------------------
# HANDS-ON PRACTICE SYSTEM (CRITICAL FOR SKILL BUILDING)
# -------------------------

class PracticeExercise(BaseModel):
    exercise: str
    difficulty: Literal["easy", "medium", "hard"]
    solution_hint: Optional[str]


class PracticeSection(BaseModel):
    exercises: List[PracticeExercise]


# -------------------------
# COMMON MISTAKES (LEARNING ACCELERATION)
# -------------------------

class CommonMistake(BaseModel):
    mistake: str
    why_it_happens: str
    fix: str


class MistakesSection(BaseModel):
    mistakes: List[CommonMistake]


# -------------------------
# DEBUGGING / TROUBLESHOOTING (REAL-WORLD READINESS)
# -------------------------

class TroubleshootingItem(BaseModel):
    problem: str
    cause: str
    solution: str


class TroubleshootingSection(BaseModel):
    issues: List[TroubleshootingItem]


# -------------------------
# SKILL VARIATIONS (REAL-WORLD FLEXIBILITY)
# -------------------------

class Variation(BaseModel):
    scenario: str
    modification: str


class VariationsSection(BaseModel):
    variations: List[Variation]


# -------------------------
# PROGRESS CHECKPOINTS (MASTERY VALIDATION)
# -------------------------

class Checkpoint(BaseModel):
    checkpoint_name: str
    criteria: str


class ProgressTracking(BaseModel):
    checkpoints: List[Checkpoint]


# -------------------------
# TOOLS & ENVIRONMENT
# -------------------------

class Tool(BaseModel):
    name: str
    purpose: str
    required: bool


class ToolsSection(BaseModel):
    tools: List[Tool]


# -------------------------
# ASSESSMENT (2026 LEARNING VALIDATION SYSTEM)
# -------------------------

class AssessmentItem(BaseModel):
    question: str
    expected_answer: str


class AssessmentSection(BaseModel):
    assessments: List[AssessmentItem]


# -------------------------
# SKILL EXTENSION (ADVANCED PATHWAYS)
# -------------------------

class SkillExtension(BaseModel):
    next_skill: str
    why_it_matters: str


class ExtensionsSection(BaseModel):
    extensions: List[SkillExtension]


# -------------------------
# SUMMARY LAYER
# -------------------------

class Summary(BaseModel):
    what_you_learned: List[str]
    skill_milestone: str


# -------------------------
# INTERNAL LINKING (TOPICAL LEARNING SYSTEM)
# -------------------------

class InternalLink(BaseModel):
    anchor_text: str
    target_page: str
    purpose: Optional[str]


class InternalLinking(BaseModel):
    links: List[InternalLink]


# -------------------------
# FINAL TUTORIAL SCHEMA
# -------------------------

class TutorialOutline(BaseModel):
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
        "Instructional",
        "Guided",
        "Educational",
        "Practical",
        "Supportive"
    ]

    # Core learning structure
    hero: TutorialHero
    skill_context: SkillContext
    prerequisites: PrerequisitesSection

    # Core learning system
    modules: ModuleSection

    # Step-level execution detail (optional deeper breakdown)
    steps: Optional[StepSection]

    # Practice system (core differentiator vs how-to guides)
    practice: PracticeSection

    # Error prevention system
    mistakes: MistakesSection
    troubleshooting: TroubleshootingSection

    # Adaptability system
    variations: VariationsSection

    # Validation system
    progress_tracking: ProgressTracking
    assessment: AssessmentSection

    # Tooling layer
    tools: ToolsSection

    # Advanced learning progression
    extensions: ExtensionsSection

    # Internal knowledge system
    internal_links: InternalLinking

    # Summary layer
    summary: Summary

    # Optimization Layer (2026 informational learning standard)
    content_goal: Literal[
        "teach_skill",
        "enable_practical_execution",
        "build_mastery",
        "reduce_learning_curve"
    ]

    success_metric: str = Field(
        default="User can independently perform the skill in real-world conditions"
    )

    target_word_count: int = Field(
        default=2000,
        ge=1500,
        le=3000,
        description="Tutorials are deep learning content"
    )