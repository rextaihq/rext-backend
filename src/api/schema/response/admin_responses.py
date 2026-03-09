from pydantic import BaseModel
from typing import List, Any, Optional

class CleanupResponse(BaseModel):
    deleted_count: int
    message: str

class PendingDeletionsResponse(BaseModel):
    pending_deletions: List[Any]
    count: int

class UserStatusActionResponse(BaseModel):
    user_id: str
    full_name: Optional[str] = None
    email: str
    old_status: str
    new_status: str
    changed_by: Optional[str] = None
    reason: Optional[str] = None
    changed_at: str

class DeactivateAccountResponseSchema(BaseModel):
    message: str
    user_id: str
    deactivated_at: Optional[str] = None

class UserPermissionsResponse(BaseModel):
    permissions: List[Any]
    roles: List[Any]
    workspace_id: Optional[str] = None
