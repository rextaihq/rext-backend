from pydantic import BaseModel
from typing import List, Optional, Dict, Any

class MemberRole(BaseModel):
    id: str
    name: str
    display_name: str

class MemberUserSimple(BaseModel):
    id: str
    name: str
    email: str
    avatar: Optional[str]
    display_name: str
    is_verified: bool

class WorkspaceMember(BaseModel):
    id: str
    user_id: str
    workspace_id: str
    status: str
    is_default: bool
    joined_at: Optional[str]
    last_activity_at: Optional[str]
    role: Optional[MemberRole]
    user: MemberUserSimple

class MemberListResponse(BaseModel):
    members: List[WorkspaceMember]
    total_count: int

class SingleMemberResponse(BaseModel):
    member: WorkspaceMember

class MemberRemoveResponse(BaseModel):
    member_id: str

class MemberUpdateRoleResponse(BaseModel):
    member: Dict[str, Any] # Can be more specific but it varies slightly
