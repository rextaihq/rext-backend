from pydantic import BaseModel
from typing import List, Optional, Literal
from uuid import UUID
from src.api.schema.user_schema import UserResponse

# Sortable columns for GET /user/users. Whitelisted rather than resolved with
# getattr(Users, ...), which would accept properties and methods (e.g.
# "initials") and blow up inside order_by, and would expose password_hash as
# an ordering key.
UserSortField = Literal[
    "created_at",
    "updated_at",
    "email",
    "full_name",
    "display_name",
    "status",
    "last_login_at",
    "login_count",
]

class UserListPagination(BaseModel):
    page: int
    per_page: int
    total: int
    total_pages: int
    has_next: bool
    has_prev: bool

class UserListResponse(BaseModel):
    users: List[UserResponse]
    total_count: int
    workspace_id: Optional[str] = None
    pagination: UserListPagination

class UserDeleteResponse(BaseModel):
    id: UUID

class UserUpdateResponse(UserResponse):
    """User update returns flat UserResponse object."""
    pass

class UserStatsResponse(BaseModel):
    """Aggregate counts backing the User Management stat cards."""
    total: int
    active: int
    inactive: int
    suspended: int
    banned: int
    verified: int
    unverified: int
