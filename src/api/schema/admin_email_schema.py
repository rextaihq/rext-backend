from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AdminEmailLogResponse(BaseModel):
    """Serialized email log shape for admin email-management endpoints."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    to_email: str
    from_email: str
    subject: str
    status: str
    provider: str
    retry_count: int
    error_message: Optional[str] = None
    created_at: datetime
    sent_at: Optional[datetime] = None
    failed_at: Optional[datetime] = None


class ResendEmailRequest(BaseModel):
    """Request payload for batch resend operations."""

    email_log_ids: List[UUID] = Field(..., min_length=1, max_length=100)
