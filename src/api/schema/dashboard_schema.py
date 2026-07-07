from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel


class TrendPoint(BaseModel):
    date: str
    value: Optional[float] = None


class DashboardKPIs(BaseModel):
    total_articles: int
    indexed_pages: int
    organic_clicks: int
    organic_impressions: int
    average_position: Optional[float] = None
    ctr: float
    organic_traffic_trend: Optional[float] = None
    total_opportunity_score: float
    articles_requiring_update: int
    average_health_score: Optional[float] = None


class DashboardCharts(BaseModel):
    click_trend: List[TrendPoint]
    impression_trend: List[TrendPoint]
    position_trend: List[TrendPoint]
    ctr_trend: List[TrendPoint]


class ContentPerformanceDashboardResponse(BaseModel):
    """Module 1 Dashboard: 9 KPIs + 4 trend charts for a workspace."""
    workspace_id: UUID
    kpis: DashboardKPIs
    charts: DashboardCharts
