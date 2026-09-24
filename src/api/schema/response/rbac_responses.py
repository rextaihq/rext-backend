"""
RBAC Response Schemas

Pydantic models matching the exact dictionary structures returned
by RoleService and PermissionService service layer methods.

Fields verified against model to_dict() output (SerializableMixin) and
service layer methods in role_service.py and permission_service.py.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Permission schemas
# ---------------------------------------------------------------------------


class PermissionItemSchema(BaseModel):
    """
    Matches Permission.to_dict():
    SerializableMixin serialises all columns → id (UUID→str), name, display_name,
    description (optional), resource, action, created_at (ISO str), updated_at (ISO str).
    """

    id: UUID
    name: str
    display_name: Optional[str] = None
    description: Optional[str] = None
    resource: Optional[str] = None
    action: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    # Optional nested roles (present when include_roles=True)
    roles: Optional[List[RoleSummarySchema]] = None


class RoleSummarySchema(BaseModel):
    """Slim role reference used inside PermissionItemSchema.roles."""

    id: UUID
    name: str
    display_name: str
    hierarchy_level: int


# Rebuild after forward-ref resolution
PermissionItemSchema.model_rebuild()


class PaginationSchema(BaseModel):
    page: int
    per_page: int
    total: int
    total_pages: int
    has_next: bool
    has_prev: bool


class PermissionListData(BaseModel):
    """
    Matches PermissionService.list_permissions() → result["data"]:
    {
        "permissions": [...],
        "count": int,
        "pagination": {...}
    }
    """

    permissions: List[PermissionItemSchema]
    count: int
    pagination: PaginationSchema


# ---------------------------------------------------------------------------
# Role schemas
# ---------------------------------------------------------------------------


class PermissionSummarySchema(BaseModel):
    """
    Slim permission reference used inside get_role_with_permissions():
    {
        "id": str(perm.id),
        "name": perm.name,
        "display_name": perm.display_name,
        "resource": perm.resource,
        "action": perm.action,
    }
    """

    id: UUID
    name: str
    display_name: Optional[str] = None
    resource: Optional[str] = None
    action: Optional[str] = None


class RoleItemSchema(BaseModel):
    """
    Matches Role.to_dict() output.
    Columns: id, name, display_name, description, hierarchy_level,
             is_system_role, is_workspace_role, created_at, updated_at.

    When include_permissions=True the route adds: permissions: List[PermissionSummarySchema]
    """

    id: UUID
    name: str
    display_name: str
    description: Optional[str] = None
    hierarchy_level: int
    is_system_role: bool
    is_workspace_role: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    # Present only when include_permissions=True
    permissions: Optional[List[PermissionSummarySchema]] = None


class RoleListData(BaseModel):
    """
    Matches the data dict built in list_roles route:
    {"roles": [...role.to_dict()...], "count": int, "pagination": {...}}
    """

    roles: List[RoleItemSchema]
    count: int
    pagination: PaginationSchema


class DeleteRoleData(BaseModel):
    """Matches the data dict built in delete_role route: {"role_id": str}"""

    role_id: UUID


# ---------------------------------------------------------------------------
# Role-Permission assignment schemas
# ---------------------------------------------------------------------------


class AssignPermissionsData(BaseModel):
    """
    Matches PermissionService.assign_permissions_to_role() return value:
    {
        "role_id": str(role_id),
        "role_name": role.name,
        "added_count": int,
        "skipped_count": int,
        "invalid_count": int,
    }
    """

    role_id: UUID
    role_name: str
    added_count: int
    skipped_count: int
    invalid_count: int


class RevokePermissionData(BaseModel):
    """
    Matches PermissionService.revoke_permission_from_role() return value:
    {
        "role_id": str(role_id),
        "role_name": role.name,
        "permission_id": str(permission_id),
        "permission_name": permission.name,
    }
    """

    role_id: UUID
    role_name: str
    permission_id: UUID
    permission_name: str
