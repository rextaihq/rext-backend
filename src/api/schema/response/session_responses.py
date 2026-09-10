from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel


class SessionItem(BaseModel):
    id: UUID
    user_id: UUID
    token_id: Optional[str] = None
    is_current: bool
    created_at: datetime
    last_activity_at: datetime
    expires_at: datetime
    user_agent: Optional[str] = None
    ip_address: Optional[str] = None
    device_name: Optional[str] = None
    device_type: Optional[str] = None
    city: Optional[str] = None
    country: Optional[str] = None


class SessionListResponse(BaseModel):
    sessions: List[SessionItem]
    total_count: int
    active_count: int


class SessionRevokeResponse(BaseModel):
    success: bool
    session_id: UUID
    message: str


class BulkSessionRevokeResponse(BaseModel):
    revoked_count: int
    current_session_preserved: bool
