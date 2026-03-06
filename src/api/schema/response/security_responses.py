from pydantic import BaseModel
from typing import List, Optional

from src.api.schema.security_schema import (
    FailedLoginResponse,
    LockedAccountResponse,
)

class FailedLoginsListResponse(BaseModel):
    """Used for GET /security/failed-logins"""
    users: List[FailedLoginResponse]
    total: int
    limit: int
    offset: int
    has_more: bool

class LockedAccountsListResponse(BaseModel):
    """Used for GET /security/locked-accounts"""
    locked_accounts: List[LockedAccountResponse]
    total: int
    limit: int
    offset: int
    has_more: bool

class ResetAttemptsResponse(BaseModel):
    """Used for POST /security/{user_id}/reset-failed-attempts"""
    user_id: str
    email: str
    full_name: Optional[str] = None
    failed_attempts: int
    previous_attempts: int

class UserLoginHistoryEventSchema(BaseModel):
    timestamp: Optional[str] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    status: str
    action: str

class UserLoginHistoryPaginatedResponse(BaseModel):
    """Used for GET /security/login-history/{user_id}"""
    user_id: str
    full_name: Optional[str] = None
    email: str
    login_history: List[UserLoginHistoryEventSchema]
    total: int
    limit: int
    offset: int
    has_more: bool
