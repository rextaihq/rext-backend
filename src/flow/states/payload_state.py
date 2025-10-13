from typing import TypedDict, List, Optional,Dict,Any
from datetime import datetime
from langchain_core.documents import Document

class ContentMetadataSchema(TypedDict, total=False):
    content_summary: Optional[str]
    content_type: Optional[str]
    target_platform: Optional[str]
    target_industry: Optional[str]
    target_audience: Optional[List[str]]
    audience_size: Optional[str]
    complexity_level: Optional[str]
    content_tone: Optional[List[str]]
    target_region: Optional[str]
    content_objectives: Optional[List[str]]
    source_references: Optional[List[str]]
    content_word_count: Optional[int]
    reading_time_minutes: Optional[int]
    content_quality_scores: Optional[Dict[str, Any]]

class ContentSEODataSchema(TypedDict, total=False):
    content_primary_keywords: List[str]
    content_secondary_keywords: Optional[List[str]]
    content_meta_description: str
    content_search_intent: Optional[List[str]]
    content_seo_score: Optional[int]
    content_readability_score: Optional[int]


class Payload(TypedDict):
    content_id:str
    workspace_id: str
    topicId: str
    author_id: str
    assigned_to_user_id: str
    title: str
    content_language: str
    content_format: str
    content_metadata: ContentMetadataSchema
    content_seo_data: ContentSEODataSchema