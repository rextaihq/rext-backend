from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class ContentHealthScoreComponents(BaseModel):
    technical_seo: Optional[float] = None
    seo_optimization: Optional[float] = None
    content_quality: Optional[float] = None
    topical_coverage: Optional[float] = None
    freshness: Optional[float] = None
    user_engagement: Optional[float] = None


class ContentHealthScoreResponse(BaseModel):
    """Module 3 Content Health Score: composite 0-100 quality score for one article."""
    content_id: UUID
    overall: Optional[float] = None
    components: ContentHealthScoreComponents
    capped_due_to_indexing: bool = False
