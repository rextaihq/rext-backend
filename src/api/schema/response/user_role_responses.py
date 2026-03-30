from pydantic import BaseModel
from typing import List, Optional, Dict, Any

class RoleAssignmentResponse(BaseModel):
    assignment: Dict[str, Any]
    role_name: str
    role_display_name: str
    workspace_name: Optional[str] = None

class RoleRevokeResponse(BaseModel):
    user_id: str
    role_id: str
    workspace_id: Optional[str] = None
    role_name: str

class UserRolesListResponse(BaseModel):
    user_id: Optional[str] = None
    roles: List[Dict[str, Any]]
    count: int
