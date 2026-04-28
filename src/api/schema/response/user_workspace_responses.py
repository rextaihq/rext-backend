from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
from uuid import UUID
from src.api.schema.workspace_schema import WorkspaceOwnerSummary

class UserWorkspaceRole(BaseModel):
    id: UUID
    name: str
    display_name: str

class UserWorkspaceBrief(BaseModel):
    id: UUID
    name: str
    slug: str
    url: Optional[str] = None
    timezone: str
    created_at: datetime
    updated_at: datetime
    owner: Optional[WorkspaceOwnerSummary] = None
    user_role: Optional[UserWorkspaceRole] = None
    knowledge_stats: Optional[dict] = None
    members_count: int
    is_owner: bool
    status: str

class UserWorkspaceListResponse(BaseModel):
    workspaces: List[UserWorkspaceBrief]
    total_count: int
    owned_count: int
    member_count: int
