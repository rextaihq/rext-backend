from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
from uuid import UUID

class ReportPeriod(BaseModel):
    start_date: datetime
    end_date: datetime
    days: int

class RevenueSummary(BaseModel):
    mrr: float
    arr: float
    total_subscriptions: int
    active_subscriptions: int
    churn_rate_monthly: float

class PlanRevenue(BaseModel):
    plan_id: UUID
    plan_name: str
    plan_display_name: str
    subscription_count: int
    revenue_monthly: float
    revenue_yearly: float

class RevenueBreakdown(BaseModel):
    current_month: Dict[str, float]
    by_plan: List[PlanRevenue]
    growth_rate: float

class RevenueHistoryEntry(BaseModel):
    month: str
    mrr: float
    new_revenue: float
    churned_revenue: float
    net_revenue: float

class PlanDistributionEntry(BaseModel):
    plan_id: UUID
    plan_name: str
    plan_display_name: str
    subscription_count: int
    revenue_monthly: float
    revenue_yearly: float
    percentage: float

class RevenueReportResponse(BaseModel):
    """Schema for comprehensive revenue report."""
    report_period: ReportPeriod
    summary: RevenueSummary
    revenue_breakdown: RevenueBreakdown
    revenue_history: List[RevenueHistoryEntry]
    plan_distribution: List[PlanDistributionEntry]
    generated_at: datetime
    message: Optional[str] = None

class RevenueSummaryResponse(BaseModel):
    """Schema for quick revenue summary."""
    current_month: Dict[str, Any]
    previous_month: Dict[str, float]
    growth: Dict[str, float]
    quick_stats: Dict[str, float]
    message: Optional[str] = None
