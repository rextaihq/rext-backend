from pydantic import BaseModel
from typing import List, Optional, Any, Dict

class SessionItem(BaseModel):
    id: str
    user_id: str
    token_id: Optional[str] = None # Should be popped in route but included for schema safety if needed
    is_current: bool
    created_at: str
    expires_at: str
    user_agent: Optional[str] = None
    ip_address: Optional[str] = None

class SessionListResponse(BaseModel):
    sessions: List[Dict[str, Any]]
    total_count: int
    active_count: int

class SessionRevokeResponse(BaseModel):
    success: bool
    session_id: str
    message: str

class BulkSessionRevokeResponse(BaseModel):
    revoked_count: int
    current_session_preserved: bool
