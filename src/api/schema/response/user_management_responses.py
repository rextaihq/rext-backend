from pydantic import BaseModel
from typing import List, Optional
from uuid import UUID
from src.api.schema.user_schema import UserResponse

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
