from typing import List, Dict, Any, Optional
from pydantic import BaseModel

# These mirror exactly what MonitoringService.get_system_health() returns and
# what the admin monitoring cards read. Optional/defaulted fields are the ones
# that legitimately go missing on a degraded path (Redis down, scheduler off) --
# they must not be required, or a partial payload documents a contract the
# service cannot always meet.

class DatabaseHealthSchema(BaseModel):
    status: str
    response_time_ms: float = 0
    connection_count: int = 0
    max_connections: int = 0
    connections_checked_in: Optional[int] = None
    connections_checked_out: Optional[int] = None
    pool_size: Optional[int] = None
    pool_overflow: Optional[int] = None
    max_overflow: Optional[int] = None
    error: Optional[str] = None

class CacheHealthSchema(BaseModel):
    status: str
    enabled: bool = False
    hit_rate: float = 0
    # The monitoring card reads memory_used_mb; the old field name
    # (memory_usage_mb) was never emitted, so the card always showed 0 MB.
    memory_used_mb: float = 0
    memory_used_bytes: Optional[int] = None
    keyspace_hits: Optional[int] = None
    keyspace_misses: Optional[int] = None
    error: Optional[str] = None

class ApiHealthSchema(BaseModel):
    status: str
    # Averaged over the sample window, so this is fractional (e.g. 22.4).
    requests_per_minute: float = 0
    avg_response_time_ms: float = 0
    error_rate: float = 0
    sample_window_minutes: Optional[int] = None
    note: Optional[str] = None
    error: Optional[str] = None

class WorkersHealthSchema(BaseModel):
    status: str
    active_jobs: int = 0
    # failed_jobs_24h is what the dashboard reads; failed_jobs is kept as an
    # alias so either name resolves to the same number.
    failed_jobs_24h: int = 0
    failed_jobs: int = 0
    running_jobs: int = 0
    registered_jobs: Optional[int] = None
    scheduler_running: bool = False
    next_run_at: Optional[str] = None
    recent_failures: List[Dict[str, Any]] = []
    note: Optional[str] = None
    error: Optional[str] = None

class SystemHealthResponseSchema(BaseModel):
    database: DatabaseHealthSchema
    cache: CacheHealthSchema
    api: ApiHealthSchema
    workers: WorkersHealthSchema
    # The dashboard renders "Last updated" from this; it was returned by the
    # service but absent from the documented contract.
    timestamp: Optional[str] = None

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
