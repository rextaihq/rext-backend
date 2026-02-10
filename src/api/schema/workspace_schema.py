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

    # Extra fields from brand_data
    about: Optional[str] = Field(None, description="About the brand")
    customer_profile: Optional[str] = Field(None, description="Customer profile details")
    selling_position: Optional[str] = Field(None, description="Selling position of the brand")
    target_audience: Optional[str] = Field(None, description="Target audience details")
    brand_voice: Optional[str] = Field(None, description="Tone and voice of the brand")
    competitors: Optional[str] = Field(None, description="Competitors information")
    content_strategy: Optional[str] = Field(None, description="Content strategy pillars")


class WorkspaceUpdateSchema(BaseModel):
    """Schema for updating workspace metadata."""
    name: Optional[str] = Field(None, min_length=1, max_length=255, description="New workspace name")
    timezone: Optional[str] = Field(None, max_length=50, description="IANA timezone identifier (e.g., America/New_York)")
    url: Optional[str] = Field(None, max_length=2048, description="Workspace website URL")
    