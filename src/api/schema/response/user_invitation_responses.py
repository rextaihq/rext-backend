from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel


class PendingInvitationWorkspace(BaseModel):
    id: UUID
    name: str
    slug: str


class PendingInvitationRole(BaseModel):
    id: UUID
    name: str
    display_name: str


class PendingInvitationInviter(BaseModel):
    id: UUID
    name: str
    email: str


class PendingInvitation(BaseModel):
    id: UUID
    workspace: PendingInvitationWorkspace
    role: Optional[PendingInvitationRole] = None
    invited_by: Optional[PendingInvitationInviter] = None
    token: str
    expires_at: Optional[datetime] = None
    created_at: Optional[datetime] = None


class PendingInvitationsResponse(BaseModel):
    invitations: List[PendingInvitation]
    count: int


class UserDeclineInvitationResponse(BaseModel):
    invitation_id: UUID
    status: str
    declined_at: datetime
