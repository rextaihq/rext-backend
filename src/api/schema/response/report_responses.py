from uuid import UUID

from pydantic import BaseModel


class PlanRevenue(BaseModel):
    plan_id: UUID
    plan_name: str
    plan_display_name: str
    subscription_count: int
    revenue_monthly: float
    revenue_yearly: float


class RevenueHistoryEntry(BaseModel):
    month: str
    mrr: float
    new_revenue: float
    churned_revenue: float
    net_revenue: float
