from pydantic import BaseModel
from typing import List, Optional, Dict, Any

class InvitationBrief(BaseModel):
    id: str
    workspace_id: str
    email: str
    role_id: Optional[str]
    role_name: Optional[str]
    status: str
    expires_at: Optional[str]
    created_at: Optional[str]
    invited_by_user_id: Optional[str]
    invited_by_name: Optional[str]
    is_expired: bool

class InvitationListResponse(BaseModel):
    invitations: List[Any] # serialize_invitation_summary output
    total_count: int
    status_filter: Optional[str] = None

class SingleInvitationResponse(BaseModel):
    invitation: InvitationBrief

class BulkInvitationResult(BaseModel):
    email: str
    success: bool
    invitation_id: Optional[str] = None
    error_message: Optional[str] = None

class BulkInvitationResponse(BaseModel):
    total_requested: int
    successful: int
    failed: int
    results: List[BulkInvitationResult]

class RevokeInvitationResponse(BaseModel):
    invitation_id: str
    status: str
    revoked_by: str
    reason: Optional[str] = None

class AcceptInvitationResponse(BaseModel):
    invitation_id: str
    workspace_id: str
    workspace_name: Optional[str] = None
    role_id: str
    membership_id: str
    joined_at: str

class ReceivedInvitation(BaseModel):
    id: str
    workspace_id: str
    workspace_name: Optional[str]
    role_id: str
    status: str
    expires_at: Optional[str]
    created_at: Optional[str]

class ReceivedInvitationsResponse(BaseModel):
    invitations: List[ReceivedInvitation]
    total_count: int

class CreatedInvitationData(BaseModel):
    id: str
    email: str
    workspace_id: str
    workspace_name: str
    role_id: str
    role_name: str
    status: str
    expires_at: str
    created_at: str

class CreateInvitationResponse(BaseModel):
    invitation: CreatedInvitationData

class InvitationStatusResponse(BaseModel):
    status: str
    timestamp: str

