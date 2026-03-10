from pydantic import BaseModel
from typing import List, Optional, Dict, Any

class AuditLogItem(BaseModel):
    """Schema for a formatted audit log entry."""
    id: str
    user_id: Optional[str] = None
    full_name: Optional[str] = None
    user_email: Optional[str] = None
    action: str
    resource_type: Optional[str] = None
    resource_id: Optional[str] = None
    workspace_id: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    request_id: Optional[str] = None
    status: str
    created_at: Optional[str] = None

class AuditLogDetailItem(AuditLogItem):
    """Schema for audit log entry with full details."""
    old_values: Optional[Dict[str, Any]] = None
    new_values: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None

# Aliases for plural usage in admin routes
AuditLogDetailedResponse = AuditLogDetailItem

class AuditLogListResponse(BaseModel):
    """Schema for paginated audit logs response (user scoped)."""
    items: List[AuditLogItem]
    total: int
    limit: int
    offset: int
    has_more: bool
    message: Optional[str] = None

class AuditLogsListResponse(BaseModel):
    """Schema for paginated audit logs response (admin scoped)."""
    items: List[AuditLogItem]
    total: int
    limit: int
    offset: int
    has_more: bool

class AuditLogDetailListResponse(BaseModel):
    """Schema for paginated audit logs response with details (admin)."""
    items: List[AuditLogDetailItem]
    total: int
    limit: int
    offset: int
    has_more: bool
    message: Optional[str] = None

class ActionCount(BaseModel):
    action: str
    count: int

class ResourceCount(BaseModel):
    resource_type: str
    count: int

class StatusCount(BaseModel):
    status: str
    count: int

class MostActiveUser(BaseModel):
    user_id: str
    full_name: Optional[str] = None
    action_count: int

class AuditStatsOverviewResponse(BaseModel):
    """Schema for audit statistics response."""
    total_logs: int
    logs_by_action: List[ActionCount]
    logs_by_resource: List[ResourceCount]
    logs_by_status: List[StatusCount]
    most_active_users: List[MostActiveUser]
    recent_failures: List[AuditLogItem]
    analysis_period_days: int
    message: Optional[str] = None
