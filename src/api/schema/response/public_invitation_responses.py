from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class InvitationValidationDetails(BaseModel):
    id: UUID
    email: str
    expires_at: datetime
    status: str
    workspace_id: UUID
    workspace_name: str
    workspace_slug: str
    role_id: UUID
    role_name: str
    inviter_display_name: Optional[str] = None
    inviter_username: str
    inviter_first_name: str
    inviter_last_name: str
    inviter_id: Optional[UUID] = None


class InvitationValidationResponse(BaseModel):
    invitation: InvitationValidationDetails


class InvitationAcceptResponse(BaseModel):
    membership_id: UUID
    workspace_id: UUID
    workspace_name: str
    workspace_slug: str
    role: str
    already_member: bool
    message: str


class InvitationDeclineResponse(BaseModel):
    invitation_id: UUID
    status: str
