from typing import List, Optional
from pydantic import BaseModel

class TopicGeneration(BaseModel):
    wizardMode: str
    industry: str
    industry_other: Optional[str] = None

    content_type: str
    content_type_other: Optional[str] = None
    platform: Optional[str] = None
    platform_other: Optional[str] = None

    audience: List[str]

    purpose: List[str]
    purpose_other: Optional[str] = None
    tone: List[str]
    tone_other: Optional[str] = None

    notes: Optional[str] = None
    num_ideas: int
    content_timing_preference: Optional[str] = None
    content_originality_preference: Optional[str] = None
    subject: Optional[str] = None

    timestamp: str

class DeleteTopics(BaseModel):
    topic_ids: List[str]