from pydantic import BaseModel, EmailStr
from typing import List, Optional, Dict, Any
from datetime import datetime
from uuid import UUID

class UserListPagination(BaseModel):
    total: int
    page: int
    per_page: int
    pages: int

class UserListResponse(BaseModel):
    users: List[Dict[str, Any]]
    total_count: int
    workspace_id: Optional[str] = None
    pagination: UserListPagination

class UserDeleteResponse(BaseModel):
    id: str

class UserUpdateProfile(BaseModel):
    id: str
    email: str
    full_name: Optional[str] = None
    display_name: Optional[str] = None
    language: str
    timezone: str
    status: str
    updated_at: Optional[str] = None

class UserUpdateResponse(BaseModel):
    user: UserUpdateProfile
