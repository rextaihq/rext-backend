from pydantic import BaseModel, Field
from typing import List, Optional, Any, Dict
from uuid import UUID
from datetime import datetime

class TopicResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    generated_by_user_id: Optional[UUID] = None
    topic_name: str
    description: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

class TopicListResponse(BaseModel):
    topics: List[TopicResponse]
    total_count: int

class TopicDeleteResponse(BaseModel):
    message: str
    deleted_count: int

