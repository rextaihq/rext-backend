"""
User-role assignment schemas for request validation and response serialization.

This module defines Pydantic models for user-role assignment operations.
"""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime, timezone


class AssignUserRoleRequest(BaseModel):
    """Schema for assigning a role to a user."""
    role_id: str = Field(
        ...,
        description="UUID of the role to assign"
    )
    workspace_id: Optional[str] = Field(
        None,
        description="UUID of workspace for workspace-scoped role (null = global role)"
    )
    is_primary: bool = Field(
        default=False,
        description="Whether this is the user's primary role"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "role_id": "550e8400-e29b-41d4-a716-446655440000",
                "workspace_id": "550e8400-e29b-41d4-a716-446655440001",
                "is_primary": False
            }
        }


class UserRoleResponse(BaseModel):
    """Schema for user-role assignment response."""
    id: str
    user_id: str
    role_id: str
    role_name: Optional[str]
    role_display_name: Optional[str]
    workspace_id: Optional[str]
    workspace_name: Optional[str]
    is_primary: bool
    assigned_at: str
    assigned_by_user_id: Optional[str]

    class Config:
        from_attributes = True
