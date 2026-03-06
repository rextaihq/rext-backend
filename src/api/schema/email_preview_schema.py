"""
Email Preview Schemas

Request/response schemas for email preview endpoint.
"""
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, Literal
from uuid import UUID
from src.utils.invitation_utils import MIN_EXPIRY_DAYS, MAX_EXPIRY_DAYS


class AuthEmailPreviewRequest(BaseModel):
    """Request schema for previewing auth emails"""

    template_type: Literal["verification", "password_reset", "welcome"] = Field(
        ...,
        description="Type of auth email template to preview"
    )
    user_name: str = Field(
        ...,
        description="User's first name or display name",
        examples=["John Doe"]
    )
    user_email: Optional[str] = Field(
        None,
        description="User's email (for password reset)",
        examples=["john@example.com"]
    )
    token: str = Field(
        default="preview_token_123abc",
        description="Token for verification/reset (will be replaced in preview)",
        examples=["abc123xyz789"]
    )
    frontend_url: Optional[str] = Field(
        None,
        description="Frontend URL (defaults to env FRONTEND_URL)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "template_type": "verification",
                "user_name": "John Doe",
                "token": "preview_token_123"
            }
        }


class WorkspaceEmailPreviewRequest(BaseModel):
    """Request schema for previewing workspace emails"""

    template_type: Literal["invitation", "invitation_accepted", "role_changed", "member_removed"] = Field(
        ...,
        description="Type of workspace email template to preview"
    )
    workspace_name: str = Field(
        ...,
        description="Name of the workspace",
        examples=["Acme Corporation"]
    )
    workspace_description: Optional[str] = Field(
        None,
        description="Workspace description (for invitation)",
        examples=["Our main workspace for content creation"]
    )
    workspace_id: Optional[str] = Field(
        None,
        description="Workspace UUID (for URLs)",
        examples=["workspace-uuid-123"]
    )
    # User/member fields
    user_name: str = Field(
        ...,
        description="Primary user name (inviter, member, etc.)",
        examples=["John Doe"]
    )
    user_email: Optional[str] = Field(
        None,
        description="User email (for invitation accepted, member removed)",
        examples=["john@example.com"]
    )
    secondary_user_name: Optional[str] = Field(
        None,
        description="Secondary user name (for multi-user templates)",
        examples=["Jane Smith"]
    )
    # Role fields
    role_name: str = Field(
        default="Member",
        description="Role name",
        examples=["Editor", "Admin", "Viewer"]
    )
    old_role_name: Optional[str] = Field(
        None,
        description="Previous role name (for role_changed)",
        examples=["Viewer"]
    )
    # Additional fields
    invitation_token: str = Field(
        default="preview_invitation_token_123",
        description="Invitation token",
        examples=["abc123xyz789"]
    )
    expiry_days: int = Field(
        default=7,
        description="Days until expiration",
        ge=MIN_EXPIRY_DAYS,
        le=MAX_EXPIRY_DAYS
    )
    reason: Optional[str] = Field(
        None,
        description="Reason for action (for member_removed)",
        examples=["Project concluded"]
    )
    frontend_url: Optional[str] = Field(
        None,
        description="Frontend URL (defaults to env FRONTEND_URL)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "template_type": "invitation",
                "workspace_name": "Acme Corporation",
                "user_name": "John Doe",
                "role_name": "Editor",
                "expiry_days": 7
            }
        }


class EmailPreviewResponse(BaseModel):
    """Response schema for email preview"""

    html: str = Field(
        ...,
        description="Rendered HTML email content"
    )
    template_type: str = Field(
        ...,
        description="Type of template rendered"
    )
    subject: str = Field(
        ...,
        description="Suggested email subject line"
    )
    preview_text: Optional[str] = Field(
        None,
        description="Email preview text (shown in inbox)"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata about the preview"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "html": "<!DOCTYPE html><html>...</html>",
                "template_type": "verification",
                "subject": "Verify Your Email Address - REXT",
                "preview_text": "Welcome to REXT! Verify your email to get started.",
                "metadata": {
                    "template_name": "Email Verification",
                    "size_bytes": 8192
                }
            }
        }
