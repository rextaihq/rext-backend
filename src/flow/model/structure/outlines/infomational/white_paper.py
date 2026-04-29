# from typing import List, Optional, Literal
# from pydantic import BaseModel, Field, conlist


# class ResearchFinding(BaseModel):
#     """A specific research finding or data point."""
#     topic: str = Field(description="Topic or theme of the finding.")
#     data_points: List[str] = Field(description="Key statistics, results, or data points.")
#     implication: str = Field(description="What this means for the reader/industry.")


# class WhitePaperSection(BaseModel):
#     heading: str = Field(description="Section heading (e.g., 'Methodology', 'Key Trends').")
#     heading_level: Literal["H2", "H3"] = Field(description="Heading level.")
#     description: str = Field(description="Goal of this section in the paper.")
#     findings: conlist(ResearchFinding, min_length=1, max_length=5)


# class WhitePaperOutline(BaseModel):
#     title: str = Field(description="SEO-optimized white paper title (e.g., 'State of [Focus Keyphrase]').")
#     slug_suggestion: str = Field(
#         pattern=r"^[a-z0-9-]+$",
#         description="Suggested URL slug."
#     )
#     brief: str = Field(description="Overall goal and value proposition for the research.")
    
#     # Context
#     focus_keyphrase: str = Field(
#         description="The primary research topic or industry focus."
#     )
#     keywords_to_include: conlist(str, min_length=3)
#     methodology: str = Field(description="The research methodology used (e.g., 'Survey of 500 professionals').")
    
#     # Structure
#     sections: conlist(WhitePaperSection, min_length=4, max_length=12)
    
#     # Data Visualizations Planning
#     image_suggestions: List[str] = Field(
#         description="Suggested charts, graphs, or visual data points (min 3)."
#     )
    
#     # Links Planning
#     link_suggestions: List[str] = Field(
#         description="Official reports, primary sources, or related white papers."
#     )
    
#     # Schema
#     schema_type: Literal["Article", "WhitePaper", "ScholarlyArticle"] = Field(
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
#     target_word_count: int = Field(ge=2000, le=15000)


from typing import List, Optional, Literal
from pydantic import BaseModel, Field


# -------------------------
# EXECUTIVE POSITIONING
# -------------------------

class WhitePaperHero(BaseModel):
    title: str
    subtitle: str

    executive_summary: str = Field(
        description="High-level summary of problem, approach, and outcome"
    )

    key_takeaway: str


# -------------------------
# PROBLEM DEFINITION (CORE FOUNDATION)
# -------------------------

class ProblemStatement(BaseModel):
    problem: str
    industry_impact: List[str]
    urgency_level: Literal["low", "medium", "high", "critical"]


# -------------------------
# CONTEXT / BACKGROUND
# -------------------------

class BackgroundContext(BaseModel):
    historical_context: Optional[str]
    current_landscape: str
    stakeholders: List[str]


# -------------------------
# RESEARCH METHODOLOGY (CRITICAL FOR TRUST)
# -------------------------

class DataSource(BaseModel):
    source_name: str
    type: Literal["study", "survey", "report", "dataset", "expert_opinion"]
    credibility_level: Literal["high", "medium", "low"]


class Methodology(BaseModel):
    approach: str
    data_sources: List[DataSource]
    limitations: Optional[List[str]]


# -------------------------
# ANALYSIS SECTION (CORE INSIGHT ENGINE)
# -------------------------

class Insight(BaseModel):
    finding: str
    explanation: str
    evidence: Optional[str]


class AnalysisSection(BaseModel):
    insights: List[Insight]


# -------------------------
# SOLUTION FRAMEWORK (KEY VALUE DELIVERY)
# -------------------------

class SolutionComponent(BaseModel):
    name: str
    description: str
    benefits: List[str]


class SolutionFramework(BaseModel):
    components: List[SolutionComponent]


# -------------------------
# COMPARATIVE ANALYSIS (2026 EXPECTATION FOR WHITE PAPERS)
# -------------------------

class Comparison(BaseModel):
    option_a: str
    option_b: str
    differences: List[str]
    recommended_choice: str


class ComparisonSection(BaseModel):
    comparisons: List[Comparison]


# -------------------------
# USE CASES (REAL-WORLD APPLICATION)
# -------------------------

class UseCase(BaseModel):
    scenario: str
    implementation: str


class UseCaseSection(BaseModel):
    use_cases: List[UseCase]


# -------------------------
# RISK & LIMITATIONS (TRUST BUILDING)
# -------------------------

class Risk(BaseModel):
    risk: str
    impact: str
    mitigation: str


class RiskSection(BaseModel):
    risks: List[Risk]


# -------------------------
# FUTURE OUTLOOK (THOUGHT LEADERSHIP)
# -------------------------

class FutureTrend(BaseModel):
    trend: str
    implication: str


class FutureOutlook(BaseModel):
    trends: List[FutureTrend]


# -------------------------
# STRATEGIC RECOMMENDATIONS
# -------------------------

class Recommendation(BaseModel):
    recommendation: str
    rationale: str
    expected_outcome: str


class RecommendationsSection(BaseModel):
    recommendations: List[Recommendation]


# -------------------------
# DATA VISUALIZATION PLAN
# -------------------------

class Visualization(BaseModel):
    type: Literal["chart", "graph", "table", "diagram"]
    purpose: str


class VisualizationPlan(BaseModel):
    visuals: List[Visualization]


# -------------------------
# EEAT SIGNALS (ESSENTIAL FOR WHITE PAPERS IN 2026 SEO)
# -------------------------

class EEATSignals(BaseModel):
    expertise_indicators: List[str]
    authority_sources: List[str]
    trust_elements: List[str]


# -------------------------
# GLOSSARY (FOR TECHNICAL CLARITY)
# -------------------------

class GlossaryTerm(BaseModel):
    term: str
    definition: str


class GlossarySection(BaseModel):
    terms: List[GlossaryTerm]


# -------------------------
# SUMMARY LAYER
# -------------------------

class WhitePaperSummary(BaseModel):
    key_findings: List[str]
    final_conclusion: str


# -------------------------
# INTERNAL LINKING
# -------------------------

class InternalLink(BaseModel):
    anchor_text: str
    target_page: str


class InternalLinking(BaseModel):
    links: List[InternalLink]


# -------------------------
# FINAL WHITE PAPER SCHEMA
# -------------------------

class WhitePaperOutline(BaseModel):
    # Core metadata
    title: str
    slug_suggestion: str = Field(pattern=r"^[a-z0-9-]+$")
    focus_keyphrase: str

    target_audience: List[str]
    tone: Literal[
        "Authoritative",
        "Analytical",
        "Research-driven",
        "Professional",
        "Formal"
    ]

    # Core structure
    hero: WhitePaperHero

    problem_statement: ProblemStatement
    background: BackgroundContext

    # Research backbone
    methodology: Methodology

    # Core insights
    analysis: AnalysisSection

    # Solution architecture
    solution: SolutionFramework

    # Comparative intelligence
    comparison: Optional[ComparisonSection]

    # Real-world application
    use_cases: UseCaseSection

    # Risk evaluation
    risks: RiskSection

    # Future outlook
    future_outlook: FutureOutlook

    # Strategic guidance
    recommendations: RecommendationsSection

    # Supporting systems
    visuals: VisualizationPlan
    glossary: GlossarySection

    # Authority layer
    eeat: EEATSignals

    # Internal SEO structure
    internal_links: InternalLinking

    # Summary
    summary: WhitePaperSummary

    # Optimization Layer (2026 informational authority standard)
    content_goal: Literal[
        "establish_thought_leadership",
        "support_decision_making",
        "present_research_insights",
        "build_authority_in_domain"
    ]

    success_metric: str = Field(
        default="Reader can make informed strategic or technical decision"
    )

    target_word_count: int = Field(
        default=4000,
        ge=1500,
        le=15000,
        description="White papers are deep research documents"
    )