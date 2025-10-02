"""Invitation schemas for request/response validation."""
from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
from datetime import datetime


class AcceptInvitationRequest(BaseModel):
    """Schema for accepting an invitation."""
    token: str = Field(..., description="Invitation token")


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
