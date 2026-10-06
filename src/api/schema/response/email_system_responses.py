from typing import Optional

from pydantic import BaseModel


class EmailWebhookHealthResponse(BaseModel):
    """Schema for email webhook health check response."""

    status: str
    service: str
    webhook_secret_configured: bool
    message: Optional[str] = None
