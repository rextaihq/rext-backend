from pydantic import BaseModel
from typing import List, Optional, Any, Dict
from src.api.schema.workspace_schema import WorkspaceResponseSchema

class WorkspaceStatusResponse(BaseModel):
    status: str
    service: str

class WorkspaceListResponse(BaseModel):
    workspaces: List[Dict[str, Any]]
    total_count: int

class SingleWorkspaceResponse(BaseModel):
    workspace: Dict[str, Any]

class RoleData(BaseModel):
    id: str
    name: str
    display_name: str
    description: Optional[str]
    is_system_role: bool
    is_workspace_role: bool
    hierarchy_level: int
    created_at: Optional[str]
    updated_at: Optional[str]

class AvailableRolesResponse(BaseModel):
    roles: List[RoleData]
    total_count: int

class WorkspaceDeleteResponse(BaseModel):
    message: str
    recovery_period_days: int
    remaining_workspaces: int
    is_last_workspace: bool
