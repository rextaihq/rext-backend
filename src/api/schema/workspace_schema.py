from pydantic import BaseModel, HttpUrl, Field, EmailStr
from typing import Optional


class ChangeMemberRoleRequest(BaseModel):
    """Request to change a workspace member's role"""
    role_id: str = Field(..., description="UUID of the new role to assign")

    class Config:
        json_schema_extra = {
            "example": {
                "role_id": "123e4567-e89b-12d3-a456-426614174000"
            }
        }


class AddWorkspaceMemberRequest(BaseModel):
    """Request body for adding a member to a workspace."""
    email: EmailStr = Field(..., description="Email address of the user to invite")

    class Config:
        json_schema_extra = {
            "example": {
                "email": "teammate@example.com"
            }
        }


class WorkspaceSchema(BaseModel):
    name: Optional[str] = Field(None, description="Optional workspace title")
    timezone: Optional[str] = Field(None, description="IANA timezone identifier (e.g., 'America/New_York', 'UTC')")
    url: Optional[HttpUrl] = Field(None, description="Workspace URL")
