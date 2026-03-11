from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime

# --- User Scoped (Batch 6) ---
class LoginHistoryEntry(BaseModel):
    """Schema for a single login history entry."""
    timestamp: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    status: str
    action: str

class UserLoginHistoryResponse(BaseModel):
    """Schema for user-scoped login history response."""
    user_id: str
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
    timestamp: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None

class FailedLoginDetail(BaseModel):
    """Schema for last failed login detail."""
    timestamp: Optional[str] = None
    ip_address: Optional[str] = None

class UserSecurityStatsResponse(BaseModel):
    """Schema for user-scoped security statistics."""
    user_id: str
    email: str
    failed_login_attempts: int
    is_locked: bool
    locked_until: Optional[str] = None
    last_login: Optional[LoginDetail] = None
    last_failed_login: Optional[FailedLoginDetail] = None
    password_changed_at: Optional[str] = None
    active_sessions_count: int
    account_created_at: Optional[str] = None
    message: Optional[str] = None

class ActiveSessionsCountResponse(BaseModel):
    """Schema for active sessions count response."""
    user_id: str
    active_sessions_count: int
    message: Optional[str] = None

# --- Admin Scoped (Restored) ---
class FailedLoginUserItem(BaseModel):
    id: str
    email: str
    full_name: Optional[str] = None
    failed_attempts: int
    locked_until: Optional[str] = None
    last_failed_at: Optional[str] = None
    is_locked: bool

class FailedLoginsListResponse(BaseModel):
    users: List[FailedLoginUserItem]
    total: int
    limit: int
    offset: int
    has_more: bool

class LockedAccountItem(BaseModel):
    id: str
    email: str
    full_name: Optional[str] = None
    locked_until: str
    failed_attempts: int
    remaining_lock_time_minutes: int

class LockedAccountsListResponse(BaseModel):
    locked_accounts: List[LockedAccountItem]
    total: int
    limit: int
    offset: int
    has_more: bool

class ResetAttemptsResponse(BaseModel):
    user_id: str
    email: str
    full_name: Optional[str] = None
    failed_attempts: int
    previous_attempts: int

class UserLoginHistoryPaginatedResponse(BaseModel):
    user_id: str
    full_name: Optional[str] = None
    email: str
    login_history: List[LoginHistoryEntry]
    total: int
    limit: int
    offset: int
    has_more: bool
