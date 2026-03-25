from pydantic import BaseModel
from typing import List, Optional, Dict, Any

class PendingInvitationWorkspace(BaseModel):
    id: str
    name: str
    slug: str

class PendingInvitationRole(BaseModel):
    id: str
    name: str
    display_name: str

class PendingInvitationInviter(BaseModel):
    id: str
    name: str
    email: str

class PendingInvitation(BaseModel):
    id: str
    workspace: PendingInvitationWorkspace
    role: Optional[PendingInvitationRole] = None
    invited_by: Optional[PendingInvitationInviter] = None
    token: str
    expires_at: Optional[str] = None
    created_at: Optional[str] = None

class PendingInvitationsResponse(BaseModel):
    invitations: List[PendingInvitation]
    count: int

class UserDeclineInvitationResponse(BaseModel):
    invitation_id: str
    status: str
    declined_at: str
