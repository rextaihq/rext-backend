from datetime import datetime
from typing import Any, List, Optional
from uuid import UUID

from pydantic import BaseModel


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
    # When the cancelled plan's paid period ends (it doesn't renew); null without a plan.
    plan_ends_at: Optional[datetime] = None


class UserPermissionsResponse(BaseModel):
    permissions: List[str]
    roles: List[str]
    workspace_id: Optional[UUID] = None
