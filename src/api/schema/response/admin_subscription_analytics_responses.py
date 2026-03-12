"""Admin subscription analytics response schemas."""

from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime

class SubscriptionStatsResponse(BaseModel):
    """Schema for overall subscription statistics."""
    total_subscriptions: int
    active_subscriptions: int
    trial_subscriptions: int
    cancelled_subscriptions: int
    expired_subscriptions: int
    suspended_subscriptions: int
    mrr: float
    arr: float
    churn_rate_monthly: float
    trial_conversion_rate: float
    average_ltv: float
    message: Optional[str] = None

class RevenueMonthMetrics(BaseModel):
    """Schema for current month revenue metrics."""
    mrr: float
    new_revenue: float
    expansion_revenue: float
    contraction_revenue: float
    churned_revenue: float

class PlanRevenue(BaseModel):
    """Schema for revenue breakdown by plan."""
    plan_id: str
    plan_name: str
    plan_display_name: str
    subscription_count: int
    revenue_monthly: float
    revenue_yearly: float
    percentage: Optional[float] = None

class RevenueMetricsResponse(BaseModel):
    """Schema for revenue metrics response."""
    current_month: RevenueMonthMetrics
    by_plan: List[PlanRevenue]
    growth_rate: float
    message: Optional[str] = None

class ChurnAnalysisResponse(BaseModel):
    """Schema for churn analysis response."""
    period: str
    total_active_start: int
    new_subscriptions: int
    cancellations: int
    total_active_end: int
    churn_rate: float
    retention_rate: float
    cancellation_reasons: Dict[str, int]
    revenue_lost: float = 0.0
    churn_by_plan: List[Dict[str, Any]] = []
    message: Optional[str] = None

class TrialConversionResponse(BaseModel):
    """Schema for trial conversion metrics."""
    total_trials_started: int
    trials_converted: int
    trials_expired: int
    trials_active: int
    conversion_rate: float
    average_trial_length_days: float
    conversion_by_plan: List[Dict[str, Any]] = []
    message: Optional[str] = None

class RecentSubscriptionRow(BaseModel):
    """Schema for a recent subscription entry."""
    subscription_id: str
    user_email_masked: str
    user_name: str
    plan_name: str
    status: str
    start_date: Optional[str] = None

class GrowthMetrics(BaseModel):
    """Schema for growth metrics."""
    new_revenue_30d: float
    growth_rate: float

class AnalyticsOverviewResponse(BaseModel):
    """Schema for comprehensive analytics overview."""
    stats: Dict[str, Any]  # Similar to SubscriptionStatsResponse but subset
    revenue_by_plan: List[PlanRevenue]
    growth_metrics: GrowthMetrics
    recent_subscriptions: List[RecentSubscriptionRow]
    message: Optional[str] = None

class RevenueHistoryEntry(BaseModel):
    """Schema for a single monthly revenue history entry."""
    month: str
    mrr: float
    new_revenue: float
    churned_revenue: float
    net_revenue: float



class RevenueHistoryData(BaseModel):
    """Wrapper for revenue history data when success() nests a list."""
    data: List[RevenueHistoryEntry]
    message: Optional[str] = None

class PlanDistributionResponse(BaseModel):
    """Schema for plan distribution data."""
    plan_data: List[PlanRevenue]
    total_subscriptions: int
    message: Optional[str] = None

class CohortRetentionResponse(BaseModel):
    """Schema for cohort retention analysis response."""
    cohorts: List[Dict[str, Any]]
    message: Optional[str] = None
