"""
User-role assignment schemas for request validation and response serialization.

This module defines Pydantic models for user-role assignment operations.
"""

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class AssignUserRoleRequest(BaseModel):
    """Schema for assigning a role to a user."""

    role_id: str = Field(..., description="UUID of the role to assign")
    workspace_id: Optional[str] = Field(
        None, description="UUID of workspace for workspace-scoped role (null = global role)"
    )
    is_primary: bool = Field(default=False, description="Whether this is the user's primary role")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "role_id": "550e8400-e29b-41d4-a716-446655440000",
                "workspace_id": "550e8400-e29b-41d4-a716-446655440001",
                "is_primary": False,
            }
        }
    )
