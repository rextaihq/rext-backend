from pydantic import BaseModel
from typing import List, Any, Optional
from datetime import datetime
from uuid import UUID

class CleanupResponse(BaseModel):
    deleted_count: int
    message: str

class PendingDeletionsResponse(BaseModel):
    pending_deletions: List[Any]
    count: int

class UserStatusActionResponse(BaseModel):
    user_id: UUID
    full_name: Optional[str] = None
    email: str
    old_status: str
    new_status: str
    changed_by: Optional[UUID] = None
    reason: Optional[str] = None
    changed_at: datetime

class DeactivateAccountResponseSchema(BaseModel):
    message: str
    user_id: UUID
    deactivated_at: Optional[datetime] = None

class UserPermissionsResponse(BaseModel):
    permissions: List[str]
    roles: List[str]
    workspace_id: Optional[UUID] = None
