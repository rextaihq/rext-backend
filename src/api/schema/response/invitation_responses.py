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
