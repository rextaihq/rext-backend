from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel


# --- User Scoped (Batch 6) ---
class LoginHistoryEntry(BaseModel):
    """Schema for a single login history entry."""

    timestamp: Optional[datetime] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    status: str
    action: str


class UserLoginHistoryResponse(BaseModel):
    """Schema for user-scoped login history response."""

    user_id: UUID
    full_name: str
    email: str
    login_history: List[LoginHistoryEntry]
    total: int
    limit: int
    offset: int
    has_more: bool
    message: Optional[str] = None


class LoginDetail(BaseModel):
    """Schema for last login detail."""

    timestamp: Optional[datetime] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None


class FailedLoginDetail(BaseModel):
    """Schema for last failed login detail."""

    timestamp: Optional[datetime] = None
    ip_address: Optional[str] = None


class UserSecurityStatsResponse(BaseModel):
    """Schema for user-scoped security statistics."""

    user_id: UUID
    email: str
    failed_login_attempts: int
    is_locked: bool
    locked_until: Optional[datetime] = None
    last_login: Optional[LoginDetail] = None
    last_failed_login: Optional[FailedLoginDetail] = None
    password_changed_at: Optional[datetime] = None
    active_sessions_count: int
    account_created_at: Optional[datetime] = None
    message: Optional[str] = None


class ActiveSessionsCountResponse(BaseModel):
    """Schema for active sessions count response."""

    user_id: UUID
    active_sessions_count: int
    message: Optional[str] = None


# --- Admin Scoped (Restored) ---
