from pydantic import BaseModel, EmailStr
from typing import List, Optional, Dict, Any
from datetime import datetime
from uuid import UUID
from src.api.schema.user_schema import UserResponse

class UserListPagination(BaseModel):
    total: int
    page: int
    per_page: int
    pages: int

class UserListResponse(BaseModel):
    users: List[UserResponse]  # fully typed
    total_count: int
    workspace_id: Optional[UUID] = None
    pagination: UserListPagination

class UserDeleteResponse(BaseModel):
    id: UUID

class UserUpdateProfile(BaseModel):
    id: UUID
    email: str
    full_name: Optional[str] = None
    display_name: Optional[str] = None
    language: str
    timezone: str
    status: str
    updated_at: Optional[datetime] = None

class UserUpdateResponse(BaseModel):
    user: UserUpdateProfile
