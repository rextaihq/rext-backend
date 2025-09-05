from typing import List, Optional
from pydantic import BaseModel

class TopicGeneration(BaseModel):
    wizardMode: str
    industry: str
    industry_other: Optional[str] = None
    industry_specific_focus: Optional[str] = None

    content_type: str
    content_type_other: Optional[str] = None
    platform: Optional[str] = None
    platform_other: Optional[str] = None

    audience: str
    reader_level: str
    audience_size: str
    demographic_age: List[str]
    demographic_location: List[str]

    purpose: List[str]
    purpose_other: Optional[str] = None
    content_goal: List[str]
    tone: List[str]
    tone_other: Optional[str] = None

    keywords: Optional[str] = None
    notes: Optional[str] = None
    additional_notes: Optional[str] = None
    num_ideas: int
    region: Optional[str] = None
    language: Optional[str] = "english"
    content_timing_preference: Optional[str] = None
    content_originality_preference: Optional[str] = None
    fresh_vs_evergreen: Optional[str] = None
    safe_vs_original: Optional[str] = None
    exclude: Optional[str] = None
    focus: Optional[str] = None
    subject: Optional[str] = None

    timestamp: str

class DeleteTopics(BaseModel):
    topic_ids: List[str]