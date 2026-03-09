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

class WorkspaceStatsResponse(BaseModel):
    workspace_exists: bool
    content_count: int
    knowledge_items_count: int
    members_count: int
    has_content_builder: bool

class EmailTemplateDeleteResponse(BaseModel):
    template_id: str

class DefaultEmailTemplateResponse(BaseModel):
    template_type: str
    subject: str
    body: str

class BrandVoiceResponse(BaseModel):
    id: Optional[str] = None
    workspace_id: str
    about: Optional[str] = None
    customer_profile: Optional[str] = None
    selling_position: Optional[str] = None
    target_audience: List[str] = []
    brand_voice: List[str] = []
    competitors: List[str] = []
    content_strategy: List[str] = []
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

class BrandVoiceWrapperResponse(BaseModel):
    brand_voice: Optional[BrandVoiceResponse] = None

class BrandVoiceStateResponse(BaseModel):
    deleted: bool

class BrandVoiceRefreshResponse(BaseModel):
    operation_id: str

class MyWorkspacePermissionsResponse(BaseModel):
    workspace_id: str
    workspace_slug: str
    user_role: str
    permissions: List[str]

class CheckWorkspacePermissionResponse(BaseModel):
    has_permission: bool
    permission: str
    workspace_id: str

class WorkspaceRoleResponse(BaseModel):
    name: str
    display_name: str
    workspace_scoped: bool
    workspace_id: Optional[str] = None

class MemberWorkspacePermissionsResponse(BaseModel):
    user_id: str
    workspace_id: str
    roles: List[WorkspaceRoleResponse]
    permissions: List[str]


