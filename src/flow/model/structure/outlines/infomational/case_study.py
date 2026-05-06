# from typing import List, Optional, Literal
# from pydantic import BaseModel, Field, conlist


# class ResultMetric(BaseModel):
#     """A specific metric or result achieved in the case study."""
#     metric_name: str = Field(description="Name of the metric (e.g., 'Conversion Rate', 'Reduction in Cost').")
#     result_value: str = Field(description="The achievement or numeric value (e.g., '+20%', '$50,000 saved').")
#     context: Optional[str] = Field(description="Explanation of the significance of this result.")


# class CaseStudySection(BaseModel):
#     heading: str = Field(description="Section heading (e.g., 'The Challenge', 'Implementing X').")
#     heading_level: Literal["H2", "H3"] = Field(description="Heading level.")
#     description: str = Field(description="Overview of the challenges, actions, or outcomes in this stage.")
#     key_highlights: conlist(str, min_length=2, max_length=6)
#     results: Optional[List[ResultMetric]] = Field(default_factory=list, description="Specific metrics or KPIs for this stage.")


# class CaseStudyOutline(BaseModel):
#     title: str = Field(description="SEO-optimized case study title starting with focus keyphrase.")
#     slug_suggestion: str = Field(
#         pattern=r"^[a-z0-9-]+$",
#         description="Suggested URL slug."
#     )
#     brief: str = Field(description="Client/project overview and the problem solved.")
    
#     # Context
#     focus_keyphrase: str = Field(
#         description="The primary solution or service highlighted in the case study."
#     )
#     keywords_to_include: conlist(str, min_length=2)
#     client: str = Field(description="The client or subject of the study.")
    
#     # Structure
#     sections: conlist(CaseStudySection, min_length=3, max_length=10)
    
#     # Visual Storytelling
#     image_suggestions: List[str] = Field(
#         description="Suggested 'before/after' photos, client logo, or infographics (min 2)."
#     )
    
#     # Links Planning
#     link_suggestions: List[str] = Field(
#         description="Related product/service pages or client website."
#     )
    
#     # Schema
#     schema_type: Literal["Article", "NewsArticle"] = Field(
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
#     target_word_count: int = Field(ge=800, le=4000)


from typing import List, Optional, Literal
from pydantic import BaseModel, Field


# -------------------------
# HERO (RESULT-FIRST POSITIONING)
# -------------------------

class CaseStudyHero(BaseModel):
    headline: str = Field(
        description="Result-driven headline (e.g., 'How X Increased Revenue by 42% in 3 Months')"
    )
    subheadline: str = Field(
        description="Brief context about client and transformation"
    )

    key_result: str = Field(
        description="Primary measurable outcome"
    )


# -------------------------
# CLIENT PROFILE (TRUST FOUNDATION)
# -------------------------

class ClientProfile(BaseModel):
    client_name: str
    industry: str
    company_size: Optional[str]
    location: Optional[str]

    initial_state: str = Field(
        description="Client situation before engagement"
    )


# -------------------------
# PROBLEM CONTEXT (WHY THIS MATTERED)
# -------------------------

class ProblemStatement(BaseModel):
    core_problem: str
    business_impact: List[str]
    urgency_level: Literal["low", "medium", "high", "critical"]


# -------------------------
# GOALS / SUCCESS CRITERIA
# -------------------------

class Goal(BaseModel):
    objective: str
    success_metric: str


class GoalsSection(BaseModel):
    goals: List[Goal]


# -------------------------
# STRATEGY (DECISION INTELLIGENCE)
# -------------------------

class StrategyDecision(BaseModel):
    decision: str
    rationale: str


class StrategySection(BaseModel):
    overview: str
    key_decisions: List[StrategyDecision]


# -------------------------
# IMPLEMENTATION (PROCESS TRANSPARENCY)
# -------------------------

class ImplementationStep(BaseModel):
    phase: str
    actions: List[str]
    tools_used: Optional[List[str]]


class ImplementationSection(BaseModel):
    steps: List[ImplementationStep]


# -------------------------
# RESULTS (CORE PROOF ENGINE)
# -------------------------

class ResultMetric(BaseModel):
    metric_name: str
    before: Optional[str]
    after: str
    improvement: str


class ResultsSection(BaseModel):
    summary: str
    metrics: List[ResultMetric]


# -------------------------
# VISUAL PROOF (2026 EXPECTATION)
# -------------------------

class VisualProof(BaseModel):
    type: Literal["chart", "screenshot", "before_after", "dashboard"]
    description: str


class VisualSection(BaseModel):
    visuals: List[VisualProof]


# -------------------------
# CHALLENGES (REALISM + TRUST)
# -------------------------

class Challenge(BaseModel):
    challenge: str
    solution: str


class ChallengesSection(BaseModel):
    challenges: List[Challenge]


# -------------------------
# CLIENT FEEDBACK (SOCIAL PROOF)
# -------------------------

class Testimonial(BaseModel):
    quote: str
    author: str
    role: Optional[str]


class TestimonialSection(BaseModel):
    testimonials: List[Testimonial]


# -------------------------
# KEY INSIGHTS (LEARNING LAYER)
# -------------------------

class Insight(BaseModel):
    insight: str
    implication: str


class InsightsSection(BaseModel):
    insights: List[Insight]


# -------------------------
# APPLICABILITY (GENERALIZATION)
# -------------------------

class Applicability(BaseModel):
    who_can_benefit: List[str]
    scenarios: List[str]


# -------------------------
# CTA (SOFT CONVERSION LAYER)
# -------------------------

class CTASection(BaseModel):
    message: str
    action: str


# -------------------------
# INTERNAL LINKING
# -------------------------

class InternalLink(BaseModel):
    anchor_text: str
    target_page: str


class InternalLinking(BaseModel):
    links: List[InternalLink]


# -------------------------
# SUMMARY
# -------------------------

class CaseStudySummary(BaseModel):
    transformation_summary: str
    key_takeaways: List[str]


# -------------------------
# FINAL CASE STUDY SCHEMA
# -------------------------

class CaseStudyOutline(BaseModel):
    # Core metadata
    title: str
    slug_suggestion: str = Field(pattern=r"^[a-z0-9-]+$")
    focus_keyphrase: str

    target_audience: List[str]
    tone: Literal[
        "Professional",
        "Analytical",
        "Persuasive",
        "Trustworthy",
        "Narrative"
    ]

    # Core story structure
    hero: CaseStudyHero
    client: ClientProfile
    problem: ProblemStatement
    goals: GoalsSection

    # Execution story
    strategy: StrategySection
    implementation: ImplementationSection

    # Proof system
    results: ResultsSection
    visuals: VisualSection

    # Trust-building layers
    challenges: ChallengesSection
    testimonials: TestimonialSection

    # Knowledge extraction
    insights: InsightsSection
    applicability: Applicability

    # Conversion layer
    cta: CTASection

    # Internal linking
    internal_links: InternalLinking

    # Summary
    summary: CaseStudySummary

    # Optimization Layer (2026 informational + commercial hybrid)
    content_goal: Literal[
        "demonstrate_real_results",
        "build_trust",
        "showcase_solution_effectiveness",
        "support_conversion"
    ]

    success_metric: str = Field(
        default="Reader believes results are credible and achievable"
    )

    target_word_count: int = Field(
        default=1200,
        ge=800,
        le=1500,
        description="Case studies require depth but stay focused"
    )