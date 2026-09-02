"""
Permission schemas for request validation and response serialization.

This module defines Pydantic models for permission-related API operations.
"""

from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


class PermissionCreate(BaseModel):
    """Schema for creating a new permission."""

    name: str = Field(
        ...,
        min_length=2,
        max_length=150,
        description="Unique permission name (format: resource.action, e.g., 'user.read')",
    )
    display_name: str = Field(
        ..., min_length=2, max_length=200, description="Human-readable permission name"
    )
    description: Optional[str] = Field(None, description="Permission description")
    resource: str = Field(
        ...,
        min_length=1,
        max_length=50,
        description="Resource type (e.g., 'user', 'role', 'content')",
    )
    action: str = Field(
        ...,
        min_length=1,
        max_length=50,
        description="Action type (e.g., 'read', 'create', 'update', 'delete')",
    )

    @field_validator("name")
    @classmethod
    def validate_name_format(cls, v: str) -> str:
        """Validate permission name follows resource.action format."""
        if "." not in v:
            raise ValueError(
                "Permission name must follow format: resource.action (e.g., 'user.read')"
            )
        parts = v.split(".")
        if len(parts) != 2:
            raise ValueError("Permission name must have exactly one dot separator")
        if not all(part.strip() for part in parts):
            raise ValueError("Resource and action cannot be empty")
        return v.lower()  # Ensure lowercase

    class Config:
        json_schema_extra = {
            "example": {
                "name": "content.create",
                "display_name": "Create Content",
                "description": "Allows creating new content items",
                "resource": "content",
                "action": "create",
            }
        }


class PermissionUpdate(BaseModel):
    """Schema for updating a permission."""

    display_name: Optional[str] = Field(
        None, min_length=2, max_length=200, description="Human-readable permission name"
    )
    description: Optional[str] = Field(None, description="Permission description")

    class Config:
        json_schema_extra = {
            "example": {
                "display_name": "Create and Publish Content",
                "description": "Allows creating and publishing content items",
            }
        }


class RoleSummary(BaseModel):
    """Minimal role info for permission responses."""

    id: str
    name: str
    display_name: str
    hierarchy_level: int

    class Config:
        from_attributes = True


class PermissionResponse(BaseModel):
    """Schema for permission response."""

    id: str
    name: str
    display_name: Optional[str]
    description: Optional[str]
    resource: Optional[str]
    action: Optional[str]
    created_at: str

    class Config:
        from_attributes = True


class PermissionWithRoles(PermissionResponse):
    """Schema for permission with associated roles."""

    roles: List[RoleSummary] = []

    class Config:
        from_attributes = True
