from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel


class MemberRole(BaseModel):
    id: UUID
    name: str
    display_name: str


class MemberUserSimple(BaseModel):
    id: UUID
    name: str
    email: str
    avatar: Optional[str] = None
    display_name: str
    is_verified: bool


class WorkspaceMember(BaseModel):
    id: UUID
    user_id: UUID
    workspace_id: UUID
    status: str
    is_default: bool
    is_owner: bool = False
    joined_at: Optional[datetime] = None
    last_activity_at: Optional[datetime] = None
    role: Optional[MemberRole] = None
    user: MemberUserSimple


class MemberListResponse(BaseModel):
    members: List[WorkspaceMember]
    total_count: int


class MemberRemoveResponse(BaseModel):
    member_id: UUID


class MemberUpdateRoleResponse(BaseModel):
    member: WorkspaceMember
