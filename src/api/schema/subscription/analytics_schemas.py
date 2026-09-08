"""
Analytics and metrics schemas for subscription reporting.

This module defines Pydantic models for subscription analytics and statistics.
"""

from pydantic import BaseModel, ConfigDict, Field
from typing import Dict, List, Any


class SubscriptionStatsResponse(BaseModel):
    """Schema for overall subscription statistics."""
    total_subscriptions: int = Field(..., description="Total subscriptions ever created")
    active_subscriptions: int = Field(..., description="Currently active subscriptions")
    trial_subscriptions: int = Field(..., description="Subscriptions in trial")
    cancelled_subscriptions: int = Field(..., description="Cancelled subscriptions")
    expired_subscriptions: int = Field(..., description="Expired subscriptions")
    suspended_subscriptions: int = Field(..., description="Suspended subscriptions")
    mrr: float = Field(..., description="Monthly Recurring Revenue")
    arr: float = Field(..., description="Annual Recurring Revenue")
    churn_rate_monthly: float = Field(..., description="Monthly churn rate percentage")
    trial_conversion_rate: float = Field(..., description="Trial to paid conversion rate")
    average_ltv: float = Field(..., description="Average customer lifetime value estimate")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "total_subscriptions": 1250,
                "active_subscriptions": 980,
                "trial_subscriptions": 150,
                "cancelled_subscriptions": 120,
                "expired_subscriptions": 0,
                "suspended_subscriptions": 0,
                "mrr": 28420.50,
                "arr": 341046.00,
                "churn_rate_monthly": 2.3,
                "trial_conversion_rate": 68.5,
                "average_ltv": 1245.00
            }
        }
    )


class PlanBreakdown(BaseModel):
    """Schema for subscription breakdown by plan."""
    plan_id: str
    plan_name: str
    plan_display_name: str
    subscription_count: int
    revenue_monthly: float
    revenue_yearly: float

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "plan_id": "123e4567-e89b-12d3-a456-426614174000",
                "plan_name": "pro",
                "plan_display_name": "Pro Plan",
                "subscription_count": 420,
                "revenue_monthly": 12579.80,
                "revenue_yearly": 150957.60
            }
        }
    )


class RevenueMetricsResponse(BaseModel):
    """Schema for revenue metrics and breakdown."""
    current_month: Dict[str, float] = Field(..., description="Current month revenue breakdown")
    by_plan: List[PlanBreakdown] = Field(..., description="Revenue breakdown by plan")
    growth_rate: float = Field(..., description="Month-over-month growth rate")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "current_month": {
                    "mrr": 28420.50,
                    "new_revenue": 5240.00,
                    "expansion_revenue": 1850.00,
                    "contraction_revenue": -450.00,
                    "churned_revenue": -1220.00
                },
                "by_plan": [
                    {
                        "plan_id": "123e4567-e89b-12d3-a456-426614174000",
                        "plan_name": "pro",
                        "plan_display_name": "Pro Plan",
                        "subscription_count": 420,
                        "revenue_monthly": 12579.80,
                        "revenue_yearly": 150957.60
                    }
                ],
                "growth_rate": 12.5
            }
        }
    )


class ChurnAnalysisResponse(BaseModel):
    """Schema for churn analysis."""
    period: str = Field(..., description="Analysis period")
    total_active_start: int = Field(..., description="Active subscriptions at start")
    new_subscriptions: int = Field(..., description="New subscriptions in period")
    cancellations: int = Field(..., description="Cancellations in period")
    total_active_end: int = Field(..., description="Active subscriptions at end")
    churn_rate: float = Field(..., description="Churn rate percentage")
    retention_rate: float = Field(..., description="Retention rate percentage")
    cancellation_reasons: Dict[str, int] = Field(default={}, description="Breakdown of cancellation reasons")
    revenue_lost: float = Field(0.0, description="Absolute MRR value lost")
    churn_by_plan: List[Dict[str, Any]] = Field(default=[], description="Churn breakdown by plan")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "period": "last_30_days",
                "total_active_start": 1000,
                "new_subscriptions": 50,
                "cancellations": 23,
                "total_active_end": 1027,
                "churn_rate": 2.3,
                "retention_rate": 97.7,
                "cancellation_reasons": {"too_expensive": 10, "not_used": 8},
                "revenue_lost": 1220.50,
                "churn_by_plan": [{"plan_name": "Pro", "cancellations": 15}]
            }
        }
    )


class TrialConversionResponse(BaseModel):
    """Schema for trial conversion metrics."""
    total_trials_started: int = Field(..., description="Total trials started in period")
    trials_converted: int = Field(..., description="Trials converted to paid")
    trials_expired: int = Field(..., description="Trials that expired")
    trials_active: int = Field(..., description="Trials still active")
    conversion_rate: float = Field(..., description="Conversion rate percentage")
    average_trial_length_days: float = Field(..., description="Average trial duration")
    conversion_by_plan: List[Dict[str, Any]] = Field(default=[], description="Conversion breakdown by plan")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "total_trials_started": 200,
                "trials_converted": 137,
                "trials_expired": 45,
                "trials_active": 18,
                "conversion_rate": 68.5,
                "average_trial_length_days": 13.2,
                "conversion_by_plan": [{"plan_name": "Pro", "conversions": 95}]
            }
        }
    )
