from pydantic import BaseModel, ConfigDict, Field


class EEATTrustScore(BaseModel):
    """
    Content-level E-E-A-T evaluation for one generated content artifact.

    Scores are 0..100. The model intentionally excludes site-level authority,
    backlinks, traffic, reputation research, and independent claim verification.
    """

    model_config = ConfigDict(extra="ignore")

    score: float = Field(description="Overall content-level E-E-A-T score.", ge=0, le=100)
    experience: float = Field(
        description="Visible first-hand experience, testing, examples, or practical use.",
        ge=0,
        le=100,
    )
    expertise: float = Field(
        description="Depth, precision, topic understanding, nuance, and useful detail.",
        ge=0,
        le=100,
    )
    trustworthiness: float = Field(
        description="Trust created by accuracy confidence, evidence, transparency, and clarity.",
        ge=0,
        le=100,
    )
    evidence_strength: float = Field(
        description=(
            "Support from citations, sourced facts, examples, visuals, tables, or methodology."
        ),
        ge=0,
        le=100,
    )
    content_accuracy: float = Field(
        description=(
            "Internal accuracy confidence from the content and its evidence, "
            "not external fact-checking."
        ),
        ge=0,
        le=100,
    )
    transparency: float = Field(
        description=(
            "Visible author/process/disclosure/source/date context where readers expect it."
        ),
        ge=0,
        le=100,
    )
    author_identity: float = Field(
        description=(
            "How clearly the content identifies its author, reviewer, or responsible party."
        ),
        ge=0,
        le=100,
    )
    freshness: float = Field(
        description=(
            "Freshness confidence from visible dates, structured dates, "
            "or the current content-generation timestamp."
        ),
        ge=0,
        le=100,
    )
    structure_quality: float = Field(
        description="Headings, flow, examples, lists, tables, media, and scannability.",
        ge=0,
        le=100,
    )
    spam_signals: float = Field(
        description=(
            "Cleanliness from low-effort, repetitive, stuffed, or "
            "manipulative content. 100 is clean."
        ),
        ge=0,
        le=100,
    )
    link_hygiene: float = Field(
        description="Citation and outbound link hygiene visible inside the content.",
        ge=0,
        le=100,
    )
    reasoning: str = Field(description="Concise explanation of the scores.")
