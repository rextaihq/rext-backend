# from typing import List, Optional, Literal
# from pydantic import BaseModel, Field, conlist


# class ImageSuggestion(BaseModel):
#     """Suggested image or diagram for explaining a concept."""

#     description: str = Field(
#         description="Description of what the image/diagram should show (e.g., 'A diagram showing the relation between X and Y')."
#     )
#     alt_text_template: str = Field(
#         description="Template for SEO-optimized alt text."
#     )
#     section: str = Field(
#         description="Which section this image/diagram belongs to."
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


# class KeyConcept(BaseModel):
#     """A core concept defined in the explainer."""
#     term: str = Field(description="Term or concept being explained.")
#     definition: str = Field(description="Clear and concise definition.")
#     examples: Optional[List[str]] = Field(default_factory=list, description="Concrete examples of this concept.")


# class ExplainerSection(BaseModel):
#     heading: str = Field(description="Section heading text.")
#     heading_level: Literal["H2", "H3"] = Field(description="Heading level.")
#     description: str = Field(description="What this section will explain.")
#     key_points: conlist(str, min_length=2, max_length=6)
#     concepts: Optional[List[KeyConcept]] = Field(default_factory=list, description="Key concepts covered in this section.")


# class ExplainerOutline(BaseModel):
#     title: str = Field(description="SEO-optimized explainer title (e.g., 'What is [Focus Keyphrase]?').")
#     slug_suggestion: str = Field(
#         pattern=r"^[a-z0-9-]+$",
#         description="Suggested URL slug."
#     )
#     brief: str = Field(description="The primary goal of this explainer and the knowledge gap it fills.")

#     # Keyphrase Strategy
#     focus_keyphrase: str = Field(
#         description="The primary term or topic being explained."
#     )
#     keywords_to_include: conlist(str, min_length=1)

#     # Structure
#     sections: conlist(ExplainerSection, min_length=3, max_length=10)
#     faqs: Optional[List[str]] = Field(default_factory=list, description="Questions common users ask about this topic.")

#     # Images/Diagrams Planning
#     image_suggestions: List[ImageSuggestion] = Field(
#         min_length=1,
#         description="Suggested diagrams or illustrative images (min 1)."
#     )

#     # Links Planning
#     link_suggestions: List[LinkSuggestion] = Field(
#         min_length=2,
#         description="Suggested internal and outbound links (min 2)."
#     )

#     # Schema
#     schema_type: Literal["Article", "HowTo", "FAQPage"] = Field(
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
#     target_word_count: int = Field(ge=800, le=5000)


from typing import List, Literal, Optional

from pydantic import BaseModel, Field

# -------------------------
# HERO / CONCEPT POSITIONING
# -------------------------


class ExplainerHero(BaseModel):
    headline: str = Field(description="Clear concept definition title")
    subheadline: str = Field(description="What will be understood after reading")

    simplified_definition: str = Field(description="One-line simple explanation of the concept")


# -------------------------
# CONCEPT CONTEXT (WHY IT MATTERS)
# -------------------------


class ConceptContext(BaseModel):
    what_it_solves: List[str]
    why_it_matters: List[str]
    where_it_is_used: List[str]


# -------------------------
# PROGRESSIVE EXPLANATION LAYERS (CORE 2026 REQUIREMENT)
# -------------------------


class ExplanationLayer(BaseModel):
    level: Literal["beginner", "intermediate", "advanced"]
    explanation: str
    key_points: List[str]


class ProgressiveExplanation(BaseModel):
    layers: List[ExplanationLayer]


# -------------------------
# CONCEPT BREAKDOWN (STRUCTURAL DECOMPOSITION)
# -------------------------


class ConceptComponent(BaseModel):
    name: str
    description: str
    role_in_system: str


class ConceptBreakdown(BaseModel):
    components: List[ConceptComponent]


# -------------------------
# HOW IT WORKS (PROCESS MODEL)
# -------------------------


class ProcessStep(BaseModel):
    step: str
    description: str


class HowItWorks(BaseModel):
    steps: List[ProcessStep]


# -------------------------
# ANALOGIES / MENTAL MODELS (CRITICAL FOR UNDERSTANDING)
# -------------------------


class Analogy(BaseModel):
    concept_part: str
    real_world_equivalent: str
    explanation: str


class AnalogySection(BaseModel):
    analogies: List[Analogy]


# -------------------------
# MISCONCEPTIONS (VERY IMPORTANT IN 2026 AI SEARCH ERA)
# -------------------------


class Misconception(BaseModel):
    misconception: str
    correction: str
    explanation: str


class MisconceptionsSection(BaseModel):
    items: List[Misconception]


# -------------------------
# REAL-WORLD APPLICATIONS
# -------------------------


class Application(BaseModel):
    scenario: str
    usage_example: str


class ApplicationsSection(BaseModel):
    applications: List[Application]


# -------------------------
# RELATIONSHIP TO OTHER CONCEPTS (SEMANTIC SEO + AI CONTEXT)
# -------------------------


class RelatedConcept(BaseModel):
    concept: str
    relationship: str


class RelatedConcepts(BaseModel):
    items: List[RelatedConcept]


# -------------------------
# VISUAL / MEDIA REPRESENTATION
# -------------------------


class MediaSuggestion(BaseModel):
    type: Literal["diagram", "flowchart", "illustration", "animation"]
    description: str
    purpose: str


class MediaPlan(BaseModel):
    media: List[MediaSuggestion]


# -------------------------
# SUMMARY LAYER (FOR SNIPPETS + AI ANSWERS)
# -------------------------


class Summary(BaseModel):
    simple_summary: str
    technical_summary: Optional[str]


# -------------------------
# FAQ (KNOWLEDGE GAPS COVERAGE)
# -------------------------


class FAQItem(BaseModel):
    question: str
    answer: str


class FAQSection(BaseModel):
    faqs: List[FAQItem]


# -------------------------
# INTENT MODEL (INFORMATIONAL ALIGNMENT)
# -------------------------


class ExplainerIntent(BaseModel):
    intent_type: Literal["concept_explanation", "technical_understanding", "educational_learning"]
    target_depth: Literal["surface", "moderate", "deep"]


# -------------------------
# FINAL EXPLAINER SCHEMA
# -------------------------


class ExplainerOutline(BaseModel):
    # Core metadata
    title: str
    slug_suggestion: str = Field(pattern=r"^[a-z0-9-]+$")
    focus_keyphrase: str
    keywords_to_include: List[str] = Field(
        default_factory=list,
        description="Secondary and long-tail keywords to naturally incorporate throughout the page.",
    )

    target_audience: List[str]
    tone: Literal["Educational", "Simplifying", "Analytical", "Conversational", "Authoritative"]

    # Core explanation structure
    hero: ExplainerHero
    intent: ExplainerIntent
    context: ConceptContext

    # Core understanding engine
    progressive_explanation: ProgressiveExplanation

    # Structural understanding
    concept_breakdown: ConceptBreakdown

    # Process understanding
    how_it_works: HowItWorks

    # Cognitive simplification layer
    analogies: AnalogySection

    # Misconception correction layer
    misconceptions: MisconceptionsSection

    # Real-world relevance
    applications: ApplicationsSection

    # Semantic knowledge graph layer
    related_concepts: RelatedConcepts

    # Visual learning layer
    media: MediaPlan

    # Summary layer (AI + snippet optimization)
    summary: Summary

    # FAQ layer
    faqs: FAQSection

    # Optimization Layer (2026 informational content standard)
    content_goal: Literal["understand_concept", "educate_user", "build_knowledge_clarity"]

    comprehension_goal: str = Field(
        default="User fully understands concept at multiple cognitive levels"
    )

    target_reading_time_minutes: Optional[int] = Field(
        default=5, description="Explainers are optimized for fast understanding"
    )

    target_word_count: int = Field(
        default=1000, ge=400, le=4000, description="Depends on concept complexity"
    )
