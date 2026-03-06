from pydantic import BaseModel
from typing import List, Optional, Any, Dict

class AuditLogBaseResponse(BaseModel):
    id: str
    user_id: Optional[str] = None
    full_name: Optional[str] = None
    user_email: Optional[str] = None
    action: str
    resource_type: str
    resource_id: Optional[str] = None
    workspace_id: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    request_id: Optional[str] = None
    status: str
    created_at: Optional[str] = None

class AuditLogDetailedResponse(AuditLogBaseResponse):
    old_values: Optional[Dict[str, Any]] = None
    new_values: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None

class AuditLogsListResponse(BaseModel):
    items: List[AuditLogBaseResponse]
    total: int
    limit: int
    offset: int
    has_more: bool

class LogsByActionSchema(BaseModel):
    action: str
    count: int

class LogsByResourceSchema(BaseModel):
    resource_type: str
    count: int

class LogsByStatusSchema(BaseModel):
    status: str
    count: int

class MostActiveUserSchema(BaseModel):
    user_id: str
    full_name: Optional[str] = None
    action_count: int

class AuditStatsOverviewResponse(BaseModel):
    total_logs: int
    logs_by_action: List[LogsByActionSchema]
    logs_by_resource: List[LogsByResourceSchema]
    logs_by_status: List[LogsByStatusSchema]
    most_active_users: List[MostActiveUserSchema]
    recent_failures: List[AuditLogBaseResponse]
    analysis_period_days: int
