from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel


class InvitationBrief(BaseModel):
    id: UUID
    workspace_id: UUID
    email: str
    role_id: Optional[UUID] = None
    role_name: Optional[str] = None
    status: str
    expires_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    invited_by_user_id: Optional[UUID] = None
    invited_by_name: Optional[str] = None
    is_expired: bool


class InvitationListResponse(BaseModel):
    invitations: List[InvitationBrief]
    total_count: int
    status_filter: Optional[str] = None


class SingleInvitationResponse(BaseModel):
    invitation: InvitationBrief


class BulkInvitationResult(BaseModel):
    email: str
    success: bool
    invitation_id: Optional[UUID] = None
    error_message: Optional[str] = None


class BulkInvitationResponse(BaseModel):
    total_requested: int
    successful: int
    failed: int
    results: List[BulkInvitationResult]


class RevokeInvitationResponse(BaseModel):
    invitation_id: UUID
    status: str
    revoked_by: UUID
    reason: Optional[str] = None


class AcceptInvitationResponse(BaseModel):
    invitation_id: UUID
    workspace_id: UUID
    workspace_name: Optional[str] = None
    role_id: UUID
    membership_id: UUID
    joined_at: datetime


class ReceivedInvitation(BaseModel):
    id: UUID
    workspace_id: UUID
    workspace_name: Optional[str] = None
    role_id: UUID
    status: str
    expires_at: Optional[datetime] = None
    created_at: Optional[datetime] = None


class ReceivedInvitationsResponse(BaseModel):
    invitations: List[ReceivedInvitation]
    total_count: int


class CreatedInvitationData(BaseModel):
    id: UUID
    email: str
    workspace_id: UUID
    workspace_name: str
    role_id: UUID
    role_name: str
    status: str
    expires_at: datetime
    created_at: datetime


class CreateInvitationResponse(BaseModel):
    invitation: CreatedInvitationData


class InvitationStatusResponse(BaseModel):
    status: str
    timestamp: datetime
