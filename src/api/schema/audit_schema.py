"""
Audit log schemas for request validation and response serialization.

This module defines Pydantic models for audit log API operations.
"""

from pydantic import BaseModel, Field, field_validator
from typing import Optional, Dict, Any, List
from datetime import datetime
from enum import Enum


class AuditActionFilter(str, Enum):
    """Common audit actions for filtering."""
    # User actions
    USER_CREATE = "user.create"
    USER_UPDATE = "user.update"
    USER_DELETE = "user.delete"
    USER_SUSPEND = "user.suspend"
    USER_ACTIVATE = "user.activate"
    USER_BAN = "user.ban"
    USER_DEACTIVATE = "user.deactivate"

    # Role actions
    ROLE_CREATE = "role.create"
    ROLE_UPDATE = "role.update"
    ROLE_DELETE = "role.delete"
    ROLE_ASSIGN = "role.assign"
    ROLE_REVOKE = "role.revoke"

    # Permission actions
    PERMISSION_CREATE = "permission.create"
    PERMISSION_UPDATE = "permission.update"
    PERMISSION_DELETE = "permission.delete"
    PERMISSION_GRANT = "permission.grant"
    PERMISSION_DENY = "permission.deny"

    # Workspace actions
    WORKSPACE_CREATE = "workspace.create"
    WORKSPACE_UPDATE = "workspace.update"
    WORKSPACE_DELETE = "workspace.delete"

    # Invitation actions
    INVITATION_CREATE = "invitation.create"
    INVITATION_ACCEPT = "invitation.accept"
    INVITATION_REVOKE = "invitation.revoke"

    # Subscription actions
    SUBSCRIPTION_CREATE = "subscription.create"
    SUBSCRIPTION_UPGRADE = "subscription.upgrade"
    SUBSCRIPTION_CANCEL = "subscription.cancel"

    # Authentication actions
    AUTH_LOGIN = "auth.login"
    AUTH_LOGOUT = "auth.logout"
    AUTH_PASSWORD_RESET = "auth.password_reset"
    AUTH_PASSWORD_CHANGE = "auth.password_change"


class AuditResourceType(str, Enum):
    """Resource types for filtering."""
    USER = "user"
    ROLE = "role"
    PERMISSION = "permission"
    WORKSPACE = "workspace"
    INVITATION = "invitation"
    SUBSCRIPTION = "subscription"
    SESSION = "session"


class AuditStatus(str, Enum):
    """Audit log status values."""
    SUCCESS = "success"
    FAILED = "failed"
    PARTIAL = "partial"


# ============================================================================
# AUDIT LOG RESPONSE SCHEMAS
# ============================================================================

class AuditLogResponse(BaseModel):
    """Schema for audit log entry response."""
    id: str = Field(..., description="Audit log UUID")
    user_id: Optional[str] = Field(None, description="User who performed the action")
    full_name: Optional[str] = Field(None, description="Full name (denormalized)")
    user_email: Optional[str] = Field(None, description="User email (denormalized)")
    action: str = Field(..., description="Action performed")
    resource_type: str = Field(..., description="Type of resource")
    resource_id: Optional[str] = Field(None, description="ID of affected resource")
    workspace_id: Optional[str] = Field(None, description="Workspace context")
    ip_address: Optional[str] = Field(None, description="IP address of request")
    user_agent: Optional[str] = Field(None, description="User agent string")
    request_id: Optional[str] = Field(None, description="Request ID for correlation")
    status: str = Field(..., description="Action status (success/failed/partial)")
    created_at: str = Field(..., description="Timestamp of action")

    class Config:
        json_schema_extra = {
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "user_id": "123e4567-e89b-12d3-a456-426614174001",
                "full_name": "John Doe",
                "user_email": "john@example.com",
                "action": "user.suspend",
                "resource_type": "user",
                "resource_id": "123e4567-e89b-12d3-a456-426614174002",
                "workspace_id": "123e4567-e89b-12d3-a456-426614174003",
                "ip_address": "192.168.1.100",
                "user_agent": "Mozilla/5.0...",
                "request_id": "req_123abc",
                "status": "success",
                "created_at": "2025-10-02T18:30:00Z"
            }
        }


class AuditLogDetailResponse(BaseModel):
    """Schema for detailed audit log entry with change tracking."""
    id: str = Field(..., description="Audit log UUID")
    user_id: Optional[str] = Field(None, description="User who performed the action")
    full_name: Optional[str] = Field(None, description="Full name (denormalized)")
    user_email: Optional[str] = Field(None, description="User email (denormalized)")
    action: str = Field(..., description="Action performed")
    resource_type: str = Field(..., description="Type of resource")
    resource_id: Optional[str] = Field(None, description="ID of affected resource")
    workspace_id: Optional[str] = Field(None, description="Workspace context")
    ip_address: Optional[str] = Field(None, description="IP address of request")
    user_agent: Optional[str] = Field(None, description="User agent string")
    request_id: Optional[str] = Field(None, description="Request ID for correlation")
    old_values: Optional[Dict[str, Any]] = Field(None, description="Previous state")
    new_values: Optional[Dict[str, Any]] = Field(None, description="New state")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional context")
    status: str = Field(..., description="Action status (success/failed/partial)")
    error_message: Optional[str] = Field(None, description="Error message if failed")
    created_at: str = Field(..., description="Timestamp of action")

    class Config:
        json_schema_extra = {
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "user_id": "123e4567-e89b-12d3-a456-426614174001",
                "full_name": "Admin User",
                "user_email": "admin@example.com",
                "action": "user.suspend",
                "resource_type": "user",
                "resource_id": "123e4567-e89b-12d3-a456-426614174002",
                "workspace_id": None,
                "ip_address": "192.168.1.100",
                "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)...",
                "request_id": "req_123abc",
                "old_values": {"status": "active"},
                "new_values": {"status": "suspended"},
                "metadata": {"reason": "Violated terms of service"},
                "status": "success",
                "error_message": None,
                "created_at": "2025-10-02T18:30:00Z"
            }
        }


class AuditLogListResponse(BaseModel):
    """Schema for paginated audit log list response."""
    logs: List[AuditLogResponse] = Field(..., description="List of audit log entries")
    total: int = Field(..., description="Total number of matching logs")
    limit: int = Field(..., description="Results per page")
    offset: int = Field(..., description="Current offset")
    has_more: bool = Field(..., description="Whether more results exist")

    class Config:
        json_schema_extra = {
            "example": {
                "logs": [
                    {
                        "id": "123e4567-e89b-12d3-a456-426614174000",
                        "user_id": "123e4567-e89b-12d3-a456-426614174001",
                        "full_name": "John Doe",
                        "user_email": "john@example.com",
                        "action": "user.suspend",
                        "resource_type": "user",
                        "resource_id": "123e4567-e89b-12d3-a456-426614174002",
                        "workspace_id": None,
                        "ip_address": "192.168.1.100",
                        "status": "success",
                        "created_at": "2025-10-02T18:30:00Z"
                    }
                ],
                "total": 250,
                "limit": 50,
                "offset": 0,
                "has_more": True
            }
        }


# ============================================================================
# AUDIT LOG FILTER SCHEMAS
# ============================================================================

class AuditLogFilterParams(BaseModel):
    """Query parameters for filtering audit logs."""
    user_id: Optional[str] = Field(None, description="Filter by user ID")
    full_name: Optional[str] = Field(None, description="Filter by full name (partial match)")
    user_email: Optional[str] = Field(None, description="Filter by user email (partial match)")
    action: Optional[str] = Field(None, description="Filter by action (exact match or prefix)")
    resource_type: Optional[str] = Field(None, description="Filter by resource type")
    resource_id: Optional[str] = Field(None, description="Filter by resource ID")
    workspace_id: Optional[str] = Field(None, description="Filter by workspace ID")
    status: Optional[AuditStatus] = Field(None, description="Filter by status")
    date_from: Optional[str] = Field(None, description="Start date (ISO 8601)")
    date_to: Optional[str] = Field(None, description="End date (ISO 8601)")
    limit: int = Field(50, ge=1, le=1000, description="Results per page")
    offset: int = Field(0, ge=0, description="Pagination offset")

    class Config:
        json_schema_extra = {
            "example": {
                "user_id": "123e4567-e89b-12d3-a456-426614174001",
                "action": "user.suspend",
                "resource_type": "user",
                "status": "success",
                "date_from": "2025-10-01T00:00:00Z",
                "date_to": "2025-10-02T23:59:59Z",
                "limit": 50,
                "offset": 0
            }
        }


# ============================================================================
# EXPORT SCHEMAS
# ============================================================================

class AuditLogExportFormat(str, Enum):
    """Export format options."""
    JSON = "json"
    CSV = "csv"


class AuditLogExportRequest(BaseModel):
    """Schema for audit log export request."""
    format: AuditLogExportFormat = Field(
        default=AuditLogExportFormat.JSON,
        description="Export format (json or csv)"
    )
    filters: Optional[AuditLogFilterParams] = Field(
        None,
        description="Optional filters to apply to export"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "format": "csv",
                "filters": {
                    "action": "user.suspend",
                    "date_from": "2025-10-01T00:00:00Z",
                    "date_to": "2025-10-02T23:59:59Z"
                }
            }
        }


# ============================================================================
# STATISTICS SCHEMAS
# ============================================================================

class AuditLogStatsResponse(BaseModel):
    """Schema for audit log statistics."""
    total_logs: int = Field(..., description="Total audit log entries")
    logs_by_action: Dict[str, int] = Field(..., description="Count by action type")
    logs_by_resource: Dict[str, int] = Field(..., description="Count by resource type")
    logs_by_status: Dict[str, int] = Field(..., description="Count by status")
    most_active_users: List[Dict[str, Any]] = Field(..., description="Top 10 active users")
    recent_failures: int = Field(..., description="Failed actions in last 24 hours")

    class Config:
        json_schema_extra = {
            "example": {
                "total_logs": 5420,
                "logs_by_action": {
                    "user.login": 2150,
                    "user.update": 890,
                    "user.suspend": 45
                },
                "logs_by_resource": {
                    "user": 3500,
                    "workspace": 1200,
                    "role": 720
                },
                "logs_by_status": {
                    "success": 5350,
                    "failed": 65,
                    "partial": 5
                },
                "most_active_users": [
                    {
                        "user_id": "123e4567-e89b-12d3-a456-426614174001",
                        "full_name": "Admin User",
                        "action_count": 450
                    }
                ],
                "recent_failures": 12
            }
        }
