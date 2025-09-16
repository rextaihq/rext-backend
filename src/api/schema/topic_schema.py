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