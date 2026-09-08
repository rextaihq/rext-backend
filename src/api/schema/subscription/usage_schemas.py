"""
Usage tracking and trial schemas for subscription monitoring.

This module defines Pydantic models for usage statistics and trial status.
"""

from pydantic import BaseModel, ConfigDict, Field
from typing import Optional


class UsageStatsResponse(BaseModel):
    """Schema for usage statistics response."""
    subscription_id: str = Field(..., description="Subscription UUID")
    plan_name: str = Field(..., description="Current plan name")
    billing_period: str = Field(..., description="Billing period")

    # Current usage
    current_workspaces: int = Field(..., description="Current number of workspaces")
    current_topics: int = Field(..., description="Current number of topics")
    current_knowledge_items: int = Field(..., description="Current number of knowledge items")
    current_api_calls: int = Field(..., description="Current API calls this period")

    # Limits
    max_workspaces: int = Field(..., description="Maximum workspaces allowed")
    max_topics: int = Field(..., description="Maximum topics allowed")
    max_knowledge_items: int = Field(..., description="Maximum knowledge items allowed")
    max_api_calls_per_month: int = Field(..., description="Maximum API calls per month")

    # Usage percentages
    workspaces_usage_percent: float = Field(..., description="Workspaces usage percentage")
    topics_usage_percent: float = Field(..., description="Topics usage percentage")
    knowledge_items_usage_percent: float = Field(..., description="Knowledge items usage percentage")
    api_calls_usage_percent: float = Field(..., description="API calls usage percentage")

    # Reset date
    usage_reset_date: str = Field(..., description="Next usage reset date")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "subscription_id": "123e4567-e89b-12d3-a456-426614174002",
                "plan_name": "pro",
                "billing_period": "monthly",
                "current_workspaces": 3,
                "current_topics": 245,
                "current_knowledge_items": 1820,
                "current_api_calls": 12500,
                "max_workspaces": 5,
                "max_topics": 500,
                "max_knowledge_items": 5000,
                "max_api_calls_per_month": 50000,
                "workspaces_usage_percent": 60.0,
                "topics_usage_percent": 49.0,
                "knowledge_items_usage_percent": 36.4,
                "api_calls_usage_percent": 25.0,
                "usage_reset_date": "2025-11-01T00:00:00Z"
            }
        }
    )


class TrialStatusResponse(BaseModel):
    """Schema for trial status response."""
    is_trial: bool = Field(..., description="Whether subscription is in trial")
    trial_end_date: Optional[str] = Field(None, description="Trial end date")
    days_remaining: Optional[int] = Field(None, description="Days remaining in trial")
    trial_expired: bool = Field(..., description="Whether trial has expired")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "is_trial": True,
                "trial_end_date": "2025-10-15T00:00:00Z",
                "days_remaining": 8,
                "trial_expired": False
            }
        }
    )
