"""Email template schemas for request/response validation."""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, timezone


class CreateEmailTemplateRequest(BaseModel):
    """Schema for creating a new email template."""
    workspace_id: str = Field(..., description="Workspace ID")
    template_type: str = Field(..., description="Type of template (workspace_invitation, role_changed, etc.)")
    subject: str = Field(..., min_length=1, max_length=255, description="Email subject line")
    body: str = Field(..., min_length=1, description="Email body content (supports template variables)")


class UpdateEmailTemplateRequest(BaseModel):
    """Schema for updating an email template."""
    subject: Optional[str] = Field(None, min_length=1, max_length=255, description="Email subject line")
    body: Optional[str] = Field(None, min_length=1, description="Email body content")
    is_active: Optional[bool] = Field(None, description="Whether template is active")


class EmailTemplateResponse(BaseModel):
    """Schema for email template response."""
    id: str
    workspace_id: str
    template_type: str
    subject: str
    body: str
    is_active: bool
    is_default: bool
    created_by_user_id: Optional[str] = None
    created_at: str
    updated_at: Optional[str] = None


class EmailTemplateListResponse(BaseModel):
    """Schema for list of email templates."""
    templates: List[EmailTemplateResponse]
    total_count: int


class TemplateVariablesResponse(BaseModel):
    """Schema for available template variables."""
    template_type: str
    available_variables: List[dict]
    example_usage: str


class PreviewEmailRequest(BaseModel):
    """Schema for previewing an email template with sample data."""
    subject: str = Field(..., description="Email subject template")
    body: str = Field(..., description="Email body template")
    template_type: str = Field(..., description="Template type")


class PreviewEmailResponse(BaseModel):
    """Schema for preview email response."""
    subject: str
    body: str
    variables_used: List[str]
