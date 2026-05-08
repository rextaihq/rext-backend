# from typing import List, Optional
# from pydantic import Field
# from src.flow.model.structure.outlines.base import BaseOutline, Section


# class AboutUsOutline(BaseOutline):
#     """Outline for an about us / company story page."""
#     company_name: str = Field(description="The company name.")
#     mission_statement: str = Field(description="The core mission of the company.")
#     key_milestones: Optional[List[str]] = Field(description="Important dates or achievements in company history.")
#     team_members_mentioned: Optional[List[str]] = Field(description="Key founders or leaders highlighted in the story.")


from typing import List, Optional, Literal
from pydantic import BaseModel, Field


# -------------------------
# HERO / IDENTITY SECTION
# -------------------------

class AboutHero(BaseModel):
    company_name: str
    headline: str = Field(description="Clear identity statement (who you are + what you do)")
    subheadline: str = Field(description="Mission-level clarity in one sentence")

    founding_year: Optional[int]
    location: Optional[str]

    primary_cta: Optional[str] = Field(
        default="Contact Us",
        description="Light CTA (not aggressive)"
    )


# -------------------------
# MISSION + VISION
# -------------------------

class MissionVision(BaseModel):
    mission: str
    vision: Optional[str]
    core_values: List[str]


# -------------------------
# STORY (LIGHTWEIGHT, NOT BLOG-LIKE)
# -------------------------

class CompanyStory(BaseModel):
    origin_story: str = Field(description="Why the company was founded")
    problem_space: str = Field(description="What problem they are solving")
    journey_highlights: List[str]


# -------------------------
# PROOF OF LEGITIMACY (CRITICAL IN 2026)
# -------------------------

class CredibilitySignals(BaseModel):
    metrics: List[str] = Field(
        description="Numbers like users, revenue, countries, etc."
    )
    certifications: Optional[List[str]] = Field(default_factory=list)
    awards: Optional[List[str]] = Field(default_factory=list)
    press_mentions: Optional[List[str]] = Field(default_factory=list)


# -------------------------
# TEAM SECTION (HUMAN TRUST LAYER)
# -------------------------

class TeamMember(BaseModel):
    name: str
    role: str
    bio: Optional[str]
    linkedin: Optional[str]


class TeamSection(BaseModel):
    leadership: List[TeamMember]
    culture_notes: Optional[List[str]] = Field(
        default_factory=list,
        description="How the team works / culture insights"
    )


# -------------------------
# WHAT YOU DO (CLARITY SECTION)
# -------------------------

class ServicesSnapshot(BaseModel):
    offerings: List[str]
    industries_served: Optional[List[str]] = Field(default_factory=list)
    differentiators: List[str]


# -------------------------
# TRUST + SOCIAL PROOF
# -------------------------

class SocialProof(BaseModel):
    testimonials: List[str]
    client_logos: Optional[List[str]] = Field(default_factory=list)
    case_study_links: Optional[List[str]] = Field(default_factory=list)


# -------------------------
# VALUES (HUMANIZATION LAYER)
# -------------------------

class ValuesSection(BaseModel):
    values: List[str]
    principles: Optional[List[str]] = Field(default_factory=list)


# -------------------------
# CTA (SOFT NAVIGATIONAL INTENT)
# -------------------------

class CTASection(BaseModel):
    primary_cta: str
    secondary_cta: Optional[str] = None
    context_line: Optional[str] = Field(
        default=None,
        description="Soft encouragement (e.g., 'Let’s build something together')"
    )


# -------------------------
# FINAL ABOUT US PAGE SCHEMA
# -------------------------

class AboutUsOutline(BaseModel):
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
        "Professional", "Trustworthy", "Inspirational",
        "Conversational", "Authentic", "Neutral"
    ]

    # Page Structure (Trust-building flow)
    hero: AboutHero
    mission_vision: MissionVision
    company_story: CompanyStory
    services_snapshot: ServicesSnapshot
    credibility: CredibilitySignals
    social_proof: SocialProof
    team: TeamSection
    values: ValuesSection

    # CTA Layer (soft conversion)
    cta: CTASection

    # Optimization Layer (2026 standard)
    trust_intent_level: Literal[
        "low",   # curiosity
        "medium", # evaluation
        "high"   # ready to engage
    ]

    narrative_style: Literal[
        "story-driven",
        "fact-driven",
        "hybrid"
    ]

    target_word_count: int = Field(
        default=800,
        ge=400,
        le=2000,
        description="About pages are medium-length trust pages"
    )