"""
Admin and User Management Response Schemas

Pydantic models matching the exact dictionary structures returned
by UserService and RoleService for user-related management routes.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel
from .rbac_responses import PaginationSchema


# ---------------------------------------------------------------------------
# Admin Cleanup Schemas
# ---------------------------------------------------------------------------

class CleanupAccountsData(BaseModel):
    """Matches admin.cleanup_deactivated_accounts response."""
    deleted_count: int
    message: str


class PendingDeletionsData(BaseModel):
    """Matches admin.get_pending_deletions response."""
    pending_deletions: List[Dict[str, Any]]
    count: int


class CleanupTokensData(BaseModel):
    """Matches admin.cleanup_tokens response."""
    deleted_count: int
    message: str


# ---------------------------------------------------------------------------
# User Management Schemas (management.py)
# ---------------------------------------------------------------------------

class UserResponseSchema(BaseModel):
    """Basic user object schema matching Users.to_dict()."""
    id: str
    email: str
    full_name: Optional[str] = None
    display_name: Optional[str] = None
    language: Optional[str] = None
    timezone: Optional[str] = None
    status: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class UserListResponse(BaseModel):
    """Paginated user list result."""
    users: List[UserResponseSchema]
    total_count: int
    workspace_id: Optional[str] = None
    pagination: PaginationSchema


class UserDeleteResponse(BaseModel):
    """Response for user deletion."""
    id: str


# ---------------------------------------------------------------------------
# User Status Schemas (user_status.py)
# ---------------------------------------------------------------------------

class UserStatusActionResponse(BaseModel):
    """Response for user status change (suspend, ban, activate)."""
    user_id: str
    full_name: str
    email: str
    old_status: str
    new_status: str
    changed_by: str
    reason: Optional[str] = None
    changed_at: str


class DeactivateAccountResponseSchema(BaseModel):
    """Response for user self-deactivation."""
    id: str
    email: str
    status: str
    deactivated_at: str
    message: str


# ---------------------------------------------------------------------------
# User Role Assignment Schemas (roles.py & user_permissions.py)
# ---------------------------------------------------------------------------

class UserRoleAssignmentResponse(BaseModel):
    """Response for user-role assignment/revocation."""
    user_id: str
    role_id: str
    role_name: str
    workspace_id: Optional[str] = None
    is_primary: Optional[bool] = None


class UserRoleItemSchema(BaseModel):
    """Item in user roles list."""
    name: str
    display_name: str
    hierarchy_level: int
    workspace_id: Optional[str] = None


class UserRoleListResponse(BaseModel):
    """List of roles for a specific user."""
    user_id: Optional[str] = None
    roles: List[UserRoleItemSchema]
    count: int


class UserPermissionsResponse(BaseModel):
    """Response for current user permissions and roles lookup."""
    permissions: List[str]
    roles: List[UserRoleItemSchema]
    workspace_id: Optional[str] = None
