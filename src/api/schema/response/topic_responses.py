from pydantic import BaseModel, Field
from typing import List, Optional, Any, Dict
from uuid import UUID
from datetime import datetime

class TopicMetadata(BaseModel):
    title: str
    angle: str
    description: str
    channel_compatibility: List[str] = []
    target_audience: List[str] = []
    reasoning: Optional[str] = None

class PerformanceMetrics(BaseModel):
    overall_score: float
    detailed_scores: Dict[str, Any] = {}
    tags: List[str] = []

class TopicConfiguration(BaseModel):
    suggested_defaults: Dict[str, Any] = {}
    goal_alignment: Dict[str, Any] = {}
    content_guidance: Dict[str, Any] = {}
    audience_insights: Dict[str, Any] = {}
    research_config: Dict[str, Any] = {}
    user_settings: Dict[str, Any] = {}

class TopicResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    generated_by_user_id: Optional[UUID] = None
    generated_by_first_name: Optional[str] = None
    generated_by_last_name: Optional[str] = None
    approved: bool = False
    approved_at: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    # Enhanced structure from to_dict
    topic_metadata: TopicMetadata
    performance_metrics: PerformanceMetrics
    configuration: TopicConfiguration

class TopicListResponse(BaseModel):
    topics: List[TopicResponse]
    total_count: int

class TopicDeleteResponse(BaseModel):
    message: str
    deleted_count: int
