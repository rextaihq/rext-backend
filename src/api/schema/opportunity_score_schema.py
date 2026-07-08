from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel


class OpportunityScoreResponse(BaseModel):
    """Module 4 Opportunity Score: composite 0-100 score + modeled outputs for one article."""
    content_id: UUID
    score: Optional[float] = None
    estimated_traffic_gain: Optional[float] = None   # clicks/month, modeled
    estimated_ranking_gain: Optional[float] = None    # positions
    priority_level: Optional[str] = None               # Critical | High | Medium | Low
    estimated_time_to_improve: Optional[str] = None
    target_query: Optional[str] = None
    target_query_impressions: Optional[float] = None
    current_position: Optional[float] = None
    target_position: Optional[float] = None
    current_impressions: Optional[float] = None
    capped_due_to_indexing: bool = False


class OpportunityRankedItem(BaseModel):
    content_id: UUID
    title: str
    url: Optional[str] = None
    score: Optional[float] = None
    estimated_traffic_gain: Optional[float] = None
    estimated_ranking_gain: Optional[float] = None
    priority_level: Optional[str] = None
    estimated_time_to_improve: Optional[str] = None
    target_query: Optional[str] = None
    target_query_impressions: Optional[float] = None
    current_position: Optional[float] = None
    target_position: Optional[float] = None
    current_impressions: Optional[float] = None
    capped_due_to_indexing: bool = False


class OpportunityRankedListResponse(BaseModel):
    """Module 4: workspace's published articles ranked by opportunity score."""
    workspace_id: UUID
    items: List[OpportunityRankedItem]
    total_count: int
    page: int
    page_size: int
    total_pages: int
