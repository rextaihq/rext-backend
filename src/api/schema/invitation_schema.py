"""Invitation schemas for request/response validation."""
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List


class AcceptInvitationRequest(BaseModel):
    """Schema for accepting an invitation."""
    token: str = Field(..., description="Invitation token")


class CreateInvitationRequest(BaseModel):
    """Schema for creating a new invitation."""
    email: EmailStr = Field(..., description="Email address to invite")
    workspace_id: str = Field(..., description="Workspace ID")
    role_id: str = Field(..., description="Role ID to assign")
    expiry_days: Optional[int] = Field(7, ge=1, le=30, description="Days until invitation expires (1-30, default 7)")


class BulkCreateInvitationRequest(BaseModel):
    """Schema for creating multiple invitations at once."""
    emails: List[EmailStr] = Field(..., min_length=1, max_length=50, description="List of email addresses to invite (max 50)")
    workspace_id: str = Field(..., description="Workspace ID")
    role_id: str = Field(..., description="Role ID to assign to all invitees")
    expiry_days: Optional[int] = Field(7, ge=1, le=30, description="Days until invitations expire (1-30, default 7)")


class WorkspaceInvitationCreateRequest(BaseModel):
    """REST-friendly schema for creating an invitation for a specific workspace."""
    email: EmailStr = Field(..., description="Email address to invite")
    role_id: str = Field(..., description="Role ID to assign")
    expiry_days: Optional[int] = Field(7, ge=1, le=30, description="Days until invitation expires (1-30, default 7)")


class WorkspaceInvitationBulkRequest(BaseModel):
    """REST-friendly schema for creating multiple invitations for a workspace."""
    emails: List[EmailStr] = Field(
        ..., min_length=1, max_length=50, description="Email addresses to invite (max 50)"
    )
    role_id: str = Field(..., description="Role ID to assign to all invitees")
    expiry_days: Optional[int] = Field(7, ge=1, le=30, description="Days until invitations expire (1-30, default 7)")


class RevokeInvitationRequest(BaseModel):
    """Schema for revoking an invitation."""
    reason: Optional[str] = Field(None, max_length=500, description="Reason for revocation")


class InvitationResponse(BaseModel):
    """Schema for invitation response."""
    id: str
    email: str
    workspace_id: str
    workspace_name: Optional[str] = None
    role_id: str
    role_name: Optional[str] = None
    invited_by_user_id: str
    invited_by_name: Optional[str] = None
    status: str
    created_at: str
    expires_at: str
    is_expired: bool


class InvitationListResponse(BaseModel):
    """Schema for list of invitations."""
    invitations: List[InvitationResponse]
    total_count: int
    status_filter: Optional[str] = None


class BulkInvitationResult(BaseModel):
    """Result for a single invitation in bulk operation."""
    email: str
    success: bool
    invitation_id: Optional[str] = None
    error_message: Optional[str] = None


class BulkInvitationResponse(BaseModel):
    """Schema for bulk invitation response."""
    total_requested: int
    successful: int
    failed: int
    results: List[BulkInvitationResult]
