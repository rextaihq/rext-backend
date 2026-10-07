"""
Session Management Schemas

Pydantic schemas for session-related API requests and responses.
"""

from typing import Optional

from pydantic import BaseModel


class SessionResponse(BaseModel):
    """Response schema for user session details."""

    id: str
    user_id: str
    device_name: Optional[str] = None
    device_type: Optional[str] = None
    ip_address: Optional[str] = None
    country: Optional[str] = None
    city: Optional[str] = None
    is_active: bool
    is_current: bool  # True if this is the session making the request
    created_at: str
    last_activity_at: str
    expires_at: str


class SessionListResponse(BaseModel):
    """Response schema for listing user sessions."""

    sessions: list[SessionResponse]
    total_count: int
    active_count: int
