from typing import List, Dict, Any, Optional
from pydantic import BaseModel
from datetime import datetime

class ReportPeriodSchema(BaseModel):
    start_date: str
    end_date: str
    days: int

class ReportSummarySchema(BaseModel):
    mrr: float
    arr: float
    total_subscriptions: int
    active_subscriptions: int
    churn_rate_monthly: float

class RevenueByPlanSchema(BaseModel):
    plan_id: str
    plan_name: str
    plan_display_name: str
    subscription_count: int
    revenue_monthly: float
    revenue_yearly: float

class CurrentMonthRevenueSchema(BaseModel):
    mrr: float
    new_revenue: float
    expansion_revenue: float
    contraction_revenue: float
    churned_revenue: float

class RevenueBreakdownSchema(BaseModel):
    current_month: CurrentMonthRevenueSchema
    by_plan: List[RevenueByPlanSchema]
    growth_rate: float

class RevenueHistoryItemSchema(BaseModel):
    month: str
    mrr: float
    new_revenue: float
    churned_revenue: float
    net_revenue: float

class PlanDistributionItemSchema(BaseModel):
    plan_id: str
    plan_name: str
    plan_display_name: str
    subscription_count: int
    revenue_monthly: float
    revenue_yearly: float
    percentage: float

class ReportsRevenueReportSchema(BaseModel):
    report_period: ReportPeriodSchema
    summary: ReportSummarySchema
    revenue_breakdown: RevenueBreakdownSchema
    revenue_history: List[RevenueHistoryItemSchema]
    plan_distribution: List[PlanDistributionItemSchema]
    generated_at: str

class RevenueSummaryCurrentMonthSchema(BaseModel):
    mrr: float
    arr: float
    active_subscriptions: int

class RevenueSummaryPreviousMonthSchema(BaseModel):
    mrr: float

class RevenueSummaryGrowthSchema(BaseModel):
    mom_growth_rate: float
    new_revenue_30d: float

class RevenueSummaryQuickStatsSchema(BaseModel):
    churn_rate: float
    trial_conversion: float

class ReportsRevenueSummarySchema(BaseModel):
    current_month: RevenueSummaryCurrentMonthSchema
    previous_month: RevenueSummaryPreviousMonthSchema
    growth: RevenueSummaryGrowthSchema
    quick_stats: RevenueSummaryQuickStatsSchema
