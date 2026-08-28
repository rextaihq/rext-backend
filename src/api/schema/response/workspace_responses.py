from pydantic import BaseModel
from typing import List, Optional, Any, Dict
from uuid import UUID
from datetime import datetime
from src.api.schema.workspace_schema import WorkspaceResponseSchema
from src.api.schema.response.persona_responses import PersonaResponse

class WorkspaceStatusResponse(BaseModel):
    status: str
    service: str

class WorkspaceListResponse(BaseModel):
    workspaces: List[WorkspaceResponseSchema]
    total_count: int

class SingleWorkspaceResponse(BaseModel):
    workspace: WorkspaceResponseSchema

class RoleData(BaseModel):
    id: UUID
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
    workspace_id: UUID
    message: str
    recovery_period_days: int
    remaining_workspaces: int
    is_last_workspace: bool

class WorkspacePermanentDeleteResponse(BaseModel):
    workspace_id: UUID
    message: str

class WorkspaceRestoreResponse(BaseModel):
    message: str
    workspace: WorkspaceResponseSchema

class DeletedWorkspaceItem(WorkspaceResponseSchema):
    deleted_at: datetime
    recovery_deadline: datetime
    days_remaining: int

class DeletedWorkspaceListResponse(BaseModel):
    workspaces: List[DeletedWorkspaceItem]
    total_count: int

class WorkspaceStatsResponse(BaseModel):
    workspace_exists: bool
    content_count: int
    knowledge_items_count: int
    members_count: int
    topics_count: int = 0
    has_content_builder: bool

class EmailTemplateDeleteResponse(BaseModel):
    template_id: str

class DefaultEmailTemplateResponse(BaseModel):
    template_type: str
    subject: str
    body: str

class BrandVoiceResponse(BaseModel):
    id: Optional[UUID] = None
    workspace_id: UUID
    brand_name: Optional[str] = None
    about: Optional[str] = None
    customer_profile: Optional[str] = None
    selling_position: Optional[str] = None
    target_audience: List[str] = []
    brand_voice: List[str] = []
    competitors: List[str] = []
    content_pillar: List[str] = []
    content_strategy: List[str] = []
    personas: List[Any] = []
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

class BrandVoiceWrapperResponse(BaseModel):
    brand_voice: Optional[BrandVoiceResponse] = None

class BrandVoiceStateResponse(BaseModel):
    deleted: bool

class BrandVoiceRefreshResponse(BaseModel):
    operation_id: str

class MyWorkspacePermissionsResponse(BaseModel):
    workspace_id: UUID
    workspace_slug: str
    user_role: str
    permissions: List[str]

class CheckWorkspacePermissionResponse(BaseModel):
    has_permission: bool
    permission: str
    workspace_id: UUID

class WorkspaceRoleResponse(BaseModel):
    name: str
    display_name: str
    workspace_scoped: bool
    workspace_id: Optional[UUID] = None

class MemberWorkspacePermissionsResponse(BaseModel):
    user_id: UUID
    workspace_id: UUID
    roles: List[WorkspaceRoleResponse]
    permissions: List[str]


