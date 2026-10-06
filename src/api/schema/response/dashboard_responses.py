from uuid import UUID

from pydantic import BaseModel


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
    recent_activities: list = []
