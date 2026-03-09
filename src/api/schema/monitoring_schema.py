from typing import List, Dict, Any, Optional
from pydantic import BaseModel

class DatabaseHealthSchema(BaseModel):
    status: str
    response_time_ms: float
    connection_count: int

class CacheHealthSchema(BaseModel):
    status: str
    hit_rate: float
    memory_usage_mb: float

class ApiHealthSchema(BaseModel):
    status: str
    requests_per_minute: int
    avg_response_time_ms: float
    error_rate: float

class WorkersHealthSchema(BaseModel):
    status: str
    active_jobs: int
    failed_jobs: int

class SystemHealthResponseSchema(BaseModel):
    database: DatabaseHealthSchema
    cache: CacheHealthSchema
    api: ApiHealthSchema
    workers: WorkersHealthSchema

class ErrorLogItemSchema(BaseModel):
    id: str
    severity: str
    message: str
    created_at: str
    resolved: bool
    resolved_at: Optional[str] = None
    resolved_by: Optional[str] = None
    stack_trace: Optional[str] = None

class PaginationMetadataSchema(BaseModel):
    total_items: int
    total_pages: int
    current_page: int
    per_page: int
    has_next: bool
    has_previous: bool

class ErrorLogsResponseSchema(BaseModel):
    items: List[ErrorLogItemSchema]
    pagination: PaginationMetadataSchema

class UsageStatsApiSchema(BaseModel):
    total: int
    by_endpoint: List[Any]
    by_hour: List[Any]
    note: Optional[str] = None

class UsageStatsContentSchema(BaseModel):
    total: int
    successful: int
    failed: int

class UsageStatsActivitySchema(BaseModel):
    active_users: int
    new_users: int
    new_workspaces: int
    sessions: int

class UsageStatsResponseSchema(BaseModel):
    period: str
    period_start: str
    api_calls: UsageStatsApiSchema
    content_generation: UsageStatsContentSchema
    user_activity: UsageStatsActivitySchema

class UsageTrendItemSchema(BaseModel):
    date: str
    content_created: int
    active_users: int
    workspaces_created: int

class UsageTrendsResponseSchema(BaseModel):
    days: int
    trends: List[UsageTrendItemSchema]
