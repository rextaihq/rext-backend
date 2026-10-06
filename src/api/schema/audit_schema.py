"""
Audit log schemas for request validation and response serialization.

This module defines Pydantic models for audit log API operations.
"""

from datetime import datetime
from enum import Enum
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


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

    id: UUID = Field(..., description="Audit log UUID")
    user_id: Optional[UUID] = Field(None, description="User who performed the action")
    full_name: Optional[str] = Field(None, description="Full name (denormalized)")
    user_email: Optional[str] = Field(None, description="User email (denormalized)")
    action: str = Field(..., description="Action performed")
    resource_type: str = Field(..., description="Type of resource")
    resource_id: Optional[UUID] = Field(None, description="ID of affected resource")
    workspace_id: Optional[UUID] = Field(None, description="Workspace context")
    ip_address: Optional[str] = Field(None, description="IP address of request")
    user_agent: Optional[str] = Field(None, description="User agent string")
    request_id: Optional[str] = Field(None, description="Request ID for correlation")
    status: str = Field(..., description="Action status (success/failed/partial)")
    created_at: datetime = Field(..., description="Timestamp of action")

    model_config = {
        "json_schema_extra": {
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
                "created_at": "2025-10-02T18:30:00Z",
            }
        }
    }


class AuditLogListResponse(BaseModel):
    """Schema for paginated audit log list response."""

    logs: List[AuditLogResponse] = Field(..., description="List of audit log entries")
    total: int = Field(..., description="Total number of matching logs")
    limit: int = Field(..., description="Results per page")
    offset: int = Field(..., description="Current offset")
    has_more: bool = Field(..., description="Whether more results exist")

    model_config = {
        "json_schema_extra": {
            "example": {"logs": [], "total": 250, "limit": 50, "offset": 0, "has_more": True}
        }
    }


# ============================================================================
# AUDIT LOG FILTER SCHEMAS
# ============================================================================


# ============================================================================
# EXPORT SCHEMAS
# ============================================================================


class AuditLogExportFormat(str, Enum):
    """Export format options."""

    JSON = "json"
    CSV = "csv"


# ============================================================================
# STATISTICS SCHEMAS
# ============================================================================
