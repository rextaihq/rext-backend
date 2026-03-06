from typing import List, Optional, Any, Dict
from pydantic import BaseModel

class WebhookEventSchema(BaseModel):
    id: str
    event_id: str
    event_name: str
    processed: bool
    processed_at: Optional[str] = None
    error_message: Optional[str] = None
    retry_count: int
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    payload_summary: Optional[Dict[str, Any]] = None
    payload: Optional[Dict[str, Any]] = None

class WebhookEventsFiltersSchema(BaseModel):
    event_name: Optional[str] = None
    processed: Optional[bool] = None
    hours: Optional[int] = None

class WebhookEventsResponseSchema(BaseModel):
    events: List[WebhookEventSchema]
    total: int
    limit: int
    offset: int
    filters: Optional[WebhookEventsFiltersSchema] = None

class WebhookRetryResponseSchema(BaseModel):
    success: bool
    message: str
    event: Optional[WebhookEventSchema] = None

class WebhookEventTypeStatSchema(BaseModel):
    event_name: str
    total: int
    processed: int
    failed: int

class WebhookRecentErrorSchema(BaseModel):
    event_name: str
    error_message: str
    created_at: Optional[str] = None

class WebhookStatsResponseSchema(BaseModel):
    total_events: int
    processed: int
    failed: int
    pending: int
    success_rate: float
    period_hours: Optional[int] = None
    by_event_type: List[WebhookEventTypeStatSchema]
    recent_errors: List[WebhookRecentErrorSchema]
