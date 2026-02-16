from typing import List, Optional
from pydantic import BaseModel

class TopicGenerationInput(BaseModel):
    wizardMode: str
    industry: str
    industry_other: Optional[str] = None

    audience: List[str]

    purpose: List[str]
    purpose_other: Optional[str] = None
    num_topics: int
    subject: Optional[str] = None

    timestamp: str

class DeleteTopics(BaseModel):
    topic_ids: List[str]

class UpdateTopicRequest(BaseModel):
    topic_id: str
    # Optional fields that can be updated
    title: Optional[str] = None
    angle: Optional[str] = None
    description: Optional[str] = None
    channel_fit: Optional[List[str]] = None
    audience_fit: Optional[List[str]] = None
    why_it_works: Optional[str] = None
    tags: Optional[List[str]] = None
    scores: Optional[dict] = None
    approved: Optional[bool] = None