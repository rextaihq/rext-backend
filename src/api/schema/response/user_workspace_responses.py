from pydantic import BaseModel
from typing import List, Optional, Dict, Any

class UserWorkspaceRole(BaseModel):
    id: str
    name: str
    display_name: str

class UserWorkspaceBrief(BaseModel):
    id: str
    name: str
    slug: str
    url: Optional[str] = None
    timezone: str
    created_at: str
    updated_at: str
    owner: Optional[Dict[str, Any]] = None
    user_role: Optional[UserWorkspaceRole] = None
    knowledge_stats: Optional[Dict[str, int]] = None
    members_count: int
    is_owner: bool
    status: str

class UserWorkspaceListResponse(BaseModel):
    workspaces: List[UserWorkspaceBrief]
    total_count: int
    owned_count: int
    member_count: int
