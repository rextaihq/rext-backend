from pydantic import BaseModel
from typing import Optional
from uuid import UUID

class ContentStats(BaseModel):
    """Schema for content statistics in the dashboard."""
    total: int
    published: int
    draft: int

class WorkspaceDashboardResponse(BaseModel):
    """Schema for the combined workspace dashboard data."""
    workspace_id: UUID
    members: int
    content: ContentStats
    personas: int
    total_knowledge_items: int = 0
    recent_activities: list = []
