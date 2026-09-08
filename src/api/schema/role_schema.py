"""
Role schemas for request validation and response serialization.

This module defines Pydantic models for role-related API operations.
"""

from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class RoleCreate(BaseModel):
    """Schema for creating a new role."""
    name: str = Field(
        ...,
        min_length=2,
        max_length=100,
        description="Unique role name (lowercase, no spaces)",
        pattern="^[a-z0-9_]+$"
    )
    display_name: str = Field(
        ...,
        min_length=2,
        max_length=150,
        description="Human-readable role name"
    )
    description: Optional[str] = Field(
        None,
        description="Role description"
    )
    hierarchy_level: int = Field(
        default=1,
        ge=0,
        le=100,
        description="Role hierarchy (0-100, higher = more privileged)"
    )
    is_system_role: bool = Field(
        default=False,
        description="Whether this is a system role (cannot be modified/deleted)"
    )
    is_workspace_role: bool = Field(
        default=False,
        description="Whether this role can be assigned to workspace members"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "content_editor",
                "display_name": "Content Editor",
                "description": "Can create and edit content",
                "hierarchy_level": 5,
                "is_system_role": False,
                "is_workspace_role": True
            }
        }
    )


class RoleUpdate(BaseModel):
    """Schema for updating a role."""
    display_name: Optional[str] = Field(
        None,
        min_length=2,
        max_length=150,
        description="Human-readable role name"
    )
    description: Optional[str] = Field(
        None,
        description="Role description"
    )
    hierarchy_level: Optional[int] = Field(
        None,
        ge=0,
        le=100,
        description="Role hierarchy (0-100)"
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "display_name": "Senior Content Editor",
                "description": "Can create, edit, and approve content",
                "hierarchy_level": 10
            }
        }
    )


class PermissionSummary(BaseModel):
    """Minimal permission info for role responses."""
    id: str
    name: str
    display_name: str
    resource: Optional[str]
    action: Optional[str]

    model_config = ConfigDict(from_attributes=True)


class RoleResponse(BaseModel):
    """Schema for role response."""
    id: str
    name: str
    display_name: str
    description: Optional[str]
    hierarchy_level: int
    is_system_role: bool
    is_workspace_role: bool
    created_at: str
    updated_at: Optional[str]

    model_config = ConfigDict(from_attributes=True)


class RoleWithPermissions(RoleResponse):
    """Schema for role with permissions."""
    permissions: List[PermissionSummary] = []

    model_config = ConfigDict(from_attributes=True)


class AssignPermissionsRequest(BaseModel):
    """Schema for assigning permissions to a role."""
    permission_ids: List[str] = Field(
        ...,
        description="List of permission UUIDs to assign to the role",
        min_length=1
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "permission_ids": [
                    "550e8400-e29b-41d4-a716-446655440000",
                    "550e8400-e29b-41d4-a716-446655440001"
                ]
            }
        }
    )
