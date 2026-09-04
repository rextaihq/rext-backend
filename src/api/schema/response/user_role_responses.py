from pydantic import BaseModel
from typing import List, Optional
from uuid import UUID

class RoleAssignmentData(BaseModel):
    """Typed replacement for Dict[str, Any] in RoleAssignmentResponse."""
    user_id: UUID
    role_id: UUID
    workspace_id: Optional[UUID] = None
    role_name: str
    role_display_name: str

class RoleAssignmentResponse(BaseModel):
    assignment: RoleAssignmentData
    role_name: str
    role_display_name: str
    workspace_name: Optional[str] = None

class RoleRevokeResponse(BaseModel):
    user_id: UUID
    role_id: UUID
    workspace_id: Optional[UUID] = None
    role_name: str

class UserRoleItem(BaseModel):
    """Typed role item replacing Dict[str, Any]."""
    id: UUID
    name: str
    display_name: str
    workspace_id: Optional[UUID] = None
    is_system_role: Optional[bool] = None

class UserRolesListResponse(BaseModel):
    user_id: Optional[UUID] = None
    roles: List[UserRoleItem]
    count: int


class UserWorkspaceScopeItem(BaseModel):
    """A workspace the user belongs to, plus the role they hold in it."""
    workspace_id: UUID
    workspace_name: str
    current_role_display_name: Optional[str] = None


class UserWorkspaceScopeListResponse(BaseModel):
    """Workspaces available as a scope when assigning a role to a user."""
    user_id: UUID
    workspaces: List[UserWorkspaceScopeItem]
    count: int
