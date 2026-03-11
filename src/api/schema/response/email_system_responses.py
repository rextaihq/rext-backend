from pydantic import BaseModel
from typing import Optional
from src.api.schema.email_preview_schema import EmailPreviewResponse

class EmailPreviewWrappedResponse(EmailPreviewResponse):
    """Schema for email preview response with optional message."""
    message: Optional[str] = None

class EmailWebhookHealthResponse(BaseModel):
    """Schema for email webhook health check response."""
    status: str
    service: str
    webhook_secret_configured: bool
    message: Optional[str] = None
