"""Invitation schemas for request/response validation."""
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
from src.utils.invitation_utils import MIN_EXPIRY_DAYS, MAX_EXPIRY_DAYS

class AcceptInvitationRequest(BaseModel):
    """Schema for accepting an invitation."""
    token: str = Field(..., description="Invitation token")


class CreateInvitationRequest(BaseModel):
    """Schema for creating a new invitation."""
    email: EmailStr = Field(..., description="Email address to invite")
    workspace_id: str = Field(..., description="Workspace ID")
    role_id: str = Field(..., description="Role ID to assign")
    expiry_days: Optional[int] = Field(7, ge=MIN_EXPIRY_DAYS, le=MAX_EXPIRY_DAYS, description=f"Days until invitation expires ({MIN_EXPIRY_DAYS}-{MAX_EXPIRY_DAYS}, default 7)")


class BulkCreateInvitationRequest(BaseModel):
    """Schema for creating multiple invitations at once."""
    emails: List[EmailStr] = Field(..., min_length=1, max_length=50, description="List of email addresses to invite (max 50)")
    workspace_id: str = Field(..., description="Workspace ID")
    role_id: str = Field(..., description="Role ID to assign to all invitees")
    expiry_days: Optional[int] = Field(7, ge=MIN_EXPIRY_DAYS, le=MAX_EXPIRY_DAYS, description=f"Days until invitations expire ({MIN_EXPIRY_DAYS}-{MAX_EXPIRY_DAYS}, default 7)")


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

class InvitationDetailResponse(BaseModel):
    """Detailed schema for a single invitation with nested workspace/role/inviter info.

    Used by public-facing endpoints like /validate and /accept
    where the consumer needs full context.
    """
    id: str
    email: str
    status: str
    expires_at: Optional[str] = None
    created_at: Optional[str] = None
    is_expired: bool
    token: Optional[str] = None

    # Nested objects for rich context
    workspace: Optional[dict] = None
    role: Optional[dict] = None
    invited_by: Optional[dict] = None

    class Config:
        from_attributes = True


class InvitationSummaryResponse(BaseModel):
    """Flat schema for invitation lists where compact representation is preferred.

    Used by workspace-scoped list endpoints.
    """
    id: str
    email: str
    workspace_id: str
    role_id: Optional[str] = None
    role_name: Optional[str] = None
    status: str
    expires_at: Optional[str] = None
    created_at: Optional[str] = None
    invited_by_user_id: Optional[str] = None
    invited_by_name: Optional[str] = None
    is_expired: bool

    class Config:
        from_attributes = True


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

class DeclineInvitationByTokenRequest(BaseModel):
    """Request body for declining an invitation via token."""
    reason: Optional[str] = Field(
        None,
        max_length=500,
        description="Optional reason for declining the invitation"
    )