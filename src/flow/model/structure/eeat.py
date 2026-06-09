from typing import List, Literal

from pydantic import BaseModel, ConfigDict, Field


class EEATSignalScore(BaseModel):
    """Per-signal award within one E-E-A-T pillar."""

    model_config = ConfigDict(extra="ignore")

    signal_id: str = Field(description="Stable signal identifier, e.g. experience_first_person.")
    label: str = Field(description="Human-readable signal name.")
    max_points: int = Field(description="Maximum points this signal can award.", ge=0)
    awarded_points: float = Field(description="Points awarded for this signal.", ge=0)
    evidence: str = Field(
        description="Short markdown excerpt supporting the award, or 'not found'."
    )


class EEATPillarScore(BaseModel):
    """Score for one E-E-A-T pillar with per-signal breakdown."""

    model_config = ConfigDict(extra="ignore")

    score: float = Field(description="Pillar score 0-100 (sum of signal awards, capped).", ge=0, le=100)
    signals: List[EEATSignalScore] = Field(description="Per-signal scoring breakdown.")


class EEATTrustScore(BaseModel):
    """
    Content-level E-E-A-T evaluation for one generated content artifact.

    Scores are 0..100. Evaluates markdown only — no site-level authority,
    backlinks, traffic, or independent external fact-checking.
    """

    model_config = ConfigDict(extra="ignore")

    score: float = Field(description="Overall weighted trust score.", ge=0, le=100)
    status: Literal["good", "needs_work", "poor"] = Field(
        description="75-100 good, 50-74 needs_work, 0-49 poor."
    )
    experience: EEATPillarScore
    expertise: EEATPillarScore
    authoritativeness: EEATPillarScore
    trustworthiness: EEATPillarScore
    reasoning: str = Field(description="Concise explanation of the scores.")
    recommendations: List[str] = Field(
        description="Up to 6 actionable improvements.",
        max_length=6,
    )
    confidence: float = Field(
        description=(
            "Evaluator confidence in this assessment (0-100), based on content "
            "completeness and evidence coverage — NOT the E-E-A-T quality score."
        ),
        ge=0,
        le=100,
    )