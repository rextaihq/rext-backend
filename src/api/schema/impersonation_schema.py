"""
Impersonation Schema Definitions

This module contains Pydantic models for user impersonation requests and responses.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class ImpersonateStartRequest(BaseModel):
    """Request to start impersonating a user"""

    user_id: str = Field(..., description="UUID of the user to impersonate")

    model_config = ConfigDict(
        json_schema_extra={"example": {"user_id": "123e4567-e89b-12d3-a456-426614174000"}}
    )


class ImpersonationStatusResponse(BaseModel):
    """Response for impersonation status check"""

    is_impersonating: bool
    original_user_id: Optional[str] = None
    original_user_email: Optional[str] = None
    original_user_name: Optional[str] = None
    impersonated_user_id: Optional[str] = None
    impersonated_user_email: Optional[str] = None
    impersonated_user_name: Optional[str] = None
    started_at: Optional[datetime] = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "is_impersonating": True,
                "original_user_id": "123e4567-e89b-12d3-a456-426614174000",
                "original_user_email": "admin@example.com",
                "original_user_name": "Admin User",
                "impersonated_user_id": "987fcdeb-51a2-43e1-b789-123456789abc",
                "impersonated_user_email": "user@example.com",
                "impersonated_user_name": "John Doe",
                "started_at": "2025-10-03T10:00:00Z",
            }
        }
    )
