"""Subscription webhook monitoring response schemas."""

from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
from uuid import UUID

class WebhookEventRow(BaseModel):
    """Schema for a single webhook event record."""
    id: int
    event_id: str
    event_name: str
    processed: bool
    retry_count: int
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    status: str
    payload: Optional[Dict[str, Any]] = None
    minutes_since_failure: Optional[int] = None

class WebhookPagination(BaseModel):
    """Schema for webhook pagination metadata."""
    page: int
    per_page: int
    total: int
    total_pages: int

class WebhookEventSummary(BaseModel):
    """Schema for webhook event summary statistics."""
    total: int
    processed: int
    pending: int
    failed: int

class WebhookEventListResponse(BaseModel):
    """Schema for the webhook event list response data."""
    events: List[WebhookEventRow]
    pagination: WebhookPagination
    summary: WebhookEventSummary
    message: Optional[str] = None

class WebhookFailureStatsByType(BaseModel):
    """Schema for failure stats by event type."""
    event_name: str
    failure_count: int
    max_retries: int

class WebhookFailureStatistics(BaseModel):
    """Schema for webhook failure statistics."""
    total_failed: int
    time_period_hours: int
    failures_by_type: List[WebhookFailureStatsByType]

class FailedWebhookListResponse(BaseModel):
    """Schema for the failed webhook list response data."""
    failed_events: List[WebhookEventRow]
    pagination: WebhookPagination
    statistics: WebhookFailureStatistics
    message: Optional[str] = None

class WebhookRetryResponse(BaseModel):
    """Schema for the webhook retry response data."""
    success: bool
    data: Optional[WebhookEventRow] = None
    message: Optional[str] = None

class WebhookStatsPeriod(BaseModel):
    """Schema for webhook stats time period."""
    days: int
    since: str

class WebhookStatsOverall(BaseModel):
    """Schema for overall webhook statistics."""
    total_events: int
    processed: int
    failed: int
    pending: int
    success_rate: float
    failure_rate: float
    average_retries: float

class WebhookStatsByType(BaseModel):
    """Schema for webhook stats by event type."""
    event_name: str
    total: int
    processed: int
    failed: int
    success_rate: float

class WebhookErrorRow(BaseModel):
    """Schema for a recent webhook error entry."""
    event_name: str
    error_message: str
    created_at: datetime


class WebhookStatisticsResponse(BaseModel):
    """Schema for the webhook statistics response data."""
    period: WebhookStatsPeriod
    overall: WebhookStatsOverall
    by_event_type: List[WebhookStatsByType]
    event_type_breakdown: List[Dict[str, Any]] = []
    recent_errors: List[WebhookErrorRow] = []
    message: Optional[str] = None


class WebhookMonitorRow(BaseModel):
    """Schema for a single webhook monitor row (simplified event view)."""
    id: int
    event_id: str
    event_name: str
    status: str
    processed: bool
    retry_count: int
    error_message: Optional[str] = None
    created_at: datetime


class WebhookMonitorListResponse(BaseModel):
    """Schema for the webhook monitor dashboard list."""
    events: List[WebhookMonitorRow]
    pagination: WebhookPagination
    summary: WebhookEventSummary
    message: Optional[str] = None


class WebhookRetryResultResponse(BaseModel):
    """Schema for a single webhook retry result."""
    event_id: str
    success: bool
    message: str
    retry_count: Optional[int] = None


class WebhookRetryAllResponse(BaseModel):
    """Schema for the bulk retry all failed webhooks response."""
    total_retried: int
    successful: int
    failed: int
    results: Optional[List[WebhookRetryResultResponse]] = None
    message: Optional[str] = None
