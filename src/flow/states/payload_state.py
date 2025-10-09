from typing import TypedDict, List, Optional
from datetime import datetime
from langchain_core.documents import Document

# Payload: what you receive from frontend
class Payload(TypedDict):
    topicId: str
    platform: str
    contentType: str
    industry: str
    audienceSize: str
    audienceType: List[str]
    readingLevel: str
    goals: List[str]
    tone: List[str]
    region: str
    language: str
    contentLength: dict
    primaryKeywords: List[str]
    includeKeyTakeaways: bool
    researchLevel: str
    competitorAnalysis: bool
    factChecking: str
    contentFreshness: str
    # humanReviewers_ids: List[str]
    enableHumansInLoop: bool
    workspace_id: str