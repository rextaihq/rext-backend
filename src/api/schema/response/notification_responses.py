from pydantic import BaseModel
from typing import List, Optional, Any, Dict
from datetime import datetime
from uuid import UUID

class NotificationItem(BaseModel):
    """Schema for a single notification."""
    id: UUID
    user_id: UUID
    workspace_id: Optional[UUID] = None
    title: str
    message: str
    type: str
    category: Optional[str] = None
    priority: str
    status: str
    is_read: bool
    read_at: Optional[datetime] = None
    payload: Optional[Dict[str, Any]] = None
    action_url: Optional[str] = None
    action_label: Optional[str] = None
    created_at: datetime
    updated_at: datetime

class NotificationPagination(BaseModel):
    """Schema for notification pagination metadata."""
    page: int
    limit: int
    total_count: int
    total_pages: int
    has_next: bool
    has_prev: bool

class NotificationListResponse(BaseModel):
    """Schema for paginated notifications response."""
    notifications: List[NotificationItem]
    pagination: NotificationPagination
    unread_count: int

class NotificationMarkReadResponse(BaseModel):
    """Schema for marking notifications as read response."""
    marked_count: int
    marked_all: bool = False
    notification_ids: Optional[List[UUID]] = None

class NotificationClearResponse(BaseModel):
    """Schema for clearing notifications response."""
    cleared_count: int
    cleared_all_read: bool = False
    notification_ids: Optional[List[UUID]] = None

class NotificationUnreadCountResponse(BaseModel):
    """Schema for unread count response."""
    unread_count: int

class NotificationDetailResponse(BaseModel):
    """Schema for a single notification detail response."""
    notification: NotificationItem
