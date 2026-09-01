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
    """Matches the objects returned by MonitoringService.get_error_logs()."""
    id: str
    timestamp: Optional[str] = None
    severity: str
    message: str
    source: Optional[str] = None
    user_id: Optional[str] = None
    request_id: Optional[str] = None
    stack_trace: Optional[str] = None
    metadata: Dict[str, Any] = {}
    resolved: bool = False
    resolved_at: Optional[str] = None

class ErrorLogResolveResponseSchema(BaseModel):
    """Payload returned by PATCH /monitoring/error-logs/{id}/resolve."""
    id: str
    resolved: bool
    resolved_at: Optional[str] = None
    resolved_by: Optional[str] = None

class PaginationMetadataSchema(BaseModel):
    total: int
    page: int
    per_page: int
    total_pages: int

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
