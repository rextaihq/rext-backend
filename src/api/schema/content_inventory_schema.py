from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ContentInventoryItem(BaseModel):
    """One row of the Module 2 content inventory table."""
    model_config = ConfigDict(from_attributes=True)

    content_id: UUID
    url: Optional[str] = None
    title: str
    primary_keyword: Optional[str] = None
    status: str

    health_score: Optional[float] = None  # Module 3 (ContentHealthScoreService)
    opportunity_score: Optional[float] = None

    organic_clicks: Optional[float] = None
    organic_impressions: Optional[float] = None
    ctr: Optional[float] = None
    average_position: Optional[float] = None
    last_updated: Optional[datetime] = None

    # Module 5 (AI Diagnosis) — always null until that module ships.
    ai_recommendation: Optional[str] = None

    trend: Optional[str] = None  # growing | declining | stable | new | no_data
    needs_update: bool = False
    low_ctr: bool = False
    is_indexed: Optional[bool] = None
    is_cannibalized: bool = False


class ContentInventoryResponse(BaseModel):
    """Module 2 Content Inventory: paginated, filterable article table."""
    workspace_id: UUID
    items: List[ContentInventoryItem]
    total_count: int
    page: int
    page_size: int
    total_pages: int
