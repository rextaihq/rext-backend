from pydantic import BaseModel
from typing import Optional

class InvitationValidationDetails(BaseModel):
    id: str
    email: str
    expires_at: str
    status: str
    workspace_id: str
    workspace_name: str
    workspace_slug: str
    role_id: str
    role_name: str
    inviter_display_name: Optional[str] = None
    inviter_username: str
    inviter_first_name: str
    inviter_last_name: str
    inviter_id: Optional[str] = None

class InvitationValidationResponse(BaseModel):
    invitation: InvitationValidationDetails

class InvitationAcceptResponse(BaseModel):
    membership_id: str
    workspace_id: str
    workspace_name: str
    workspace_slug: str
    role: str
    already_member: bool
    message: str

class InvitationDeclineResponse(BaseModel):
    invitation_id: str
    status: str
