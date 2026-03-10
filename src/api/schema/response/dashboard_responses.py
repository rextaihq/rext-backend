from pydantic import BaseModel
from typing import Optional

class ContentStats(BaseModel):
    """Schema for content statistics in the dashboard."""
    total: int
    published: int
    draft: int

class WorkspaceDashboardResponse(BaseModel):
    """Schema for the combined workspace dashboard data."""
    workspace_id: str
    members: int
    content: ContentStats
    personas: int
    message: Optional[str] = None
