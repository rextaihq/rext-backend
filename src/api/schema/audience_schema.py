from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from uuid import UUID


class AudienceDemographics(BaseModel):
    age_range: Optional[str] = Field(None, example="25-40")
    job_titles: List[str] = Field(default_factory=list)
    seniority: Optional[str] = None
    company_size: Optional[str] = None
    location: Optional[str] = None


class AudiencePsychographics(BaseModel):
    fears: List[str] = Field(default_factory=list)
    decision_levers: List[str] = Field(default_factory=list)
    values: List[str] = Field(default_factory=list)


class AudienceExtract(BaseModel):
    """Buyer/reader persona segment extracted from website content.

    Best-effort: a single-page scrape rarely has enough signal for a full
    segment profile, so most fields are optional. This is intentionally
    separate from PersonaExtract (which is for real named people).
    """
    name: str = Field(..., description="Segment label", example="Enterprise IT Buyer")
    description: Optional[str] = Field(None)
    demographics: Optional[AudienceDemographics] = None
    pain_points: List[str] = Field(default_factory=list)
    goals: List[str] = Field(default_factory=list)
    behaviors: List[str] = Field(default_factory=list)


class AudienceCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    demographics: Optional[AudienceDemographics] = None
    psychographics: Optional[AudiencePsychographics] = None
    pain_points: List[str] = Field(default_factory=list)
    goals: List[str] = Field(default_factory=list)
    behaviors: List[str] = Field(default_factory=list)
    objections: List[str] = Field(default_factory=list)
    preferred_channels: List[str] = Field(default_factory=list)
    buying_stage: Optional[str] = None


class AudienceUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    demographics: Optional[AudienceDemographics] = None
    psychographics: Optional[AudiencePsychographics] = None
    pain_points: Optional[List[str]] = None
    goals: Optional[List[str]] = None
    behaviors: Optional[List[str]] = None
    objections: Optional[List[str]] = None
    preferred_channels: Optional[List[str]] = None
    buying_stage: Optional[str] = None


class AudienceResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    name: str
    description: Optional[str] = None
    demographics: Dict[str, Any] = {}
    psychographics: Dict[str, Any] = {}
    pain_points: List[str] = []
    goals: List[str] = []
    behaviors: List[str] = []
    objections: List[str] = []
    preferred_channels: List[str] = []
    buying_stage: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class AudienceListResponse(BaseModel):
    audiences: List[AudienceResponse]
    total_count: int
