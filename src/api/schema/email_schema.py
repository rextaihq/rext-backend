"""
Email schemas for request/response validation.

Provides Pydantic schemas for email sending, querying, and management.
"""
from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

# ============================================================================
# Request Schemas
# ============================================================================

class SendEmailRequest(BaseModel):
    """Schema for sending a single email."""
    to: EmailStr = Field(..., description="Recipient email address")
    subject: str = Field(..., min_length=1, max_length=500, description="Email subject")
    html: str = Field(..., min_length=1, description="HTML email content")
    from_email: Optional[EmailStr] = Field(None, description="Sender email (defaults to config)")
    from_name: Optional[str] = Field(None, max_length=255, description="Sender name (defaults to config)")
    cc: Optional[List[EmailStr]] = Field(None, max_length=10, description="CC recipients (max 10)")
    bcc: Optional[List[EmailStr]] = Field(None, max_length=10, description="BCC recipients (max 10)")
    reply_to: Optional[EmailStr] = Field(None, description="Reply-to email address")
    workspace_id: Optional[str] = Field(None, description="Associated workspace ID")
    user_id: Optional[str] = Field(None, description="Associated user ID")
    template_type: Optional[str] = Field(None, max_length=100, description="Email template type identifier")
    tags: Optional[Dict[str, str]] = Field(None, description="Custom tags for categorization")

    @field_validator('tags')
    @classmethod
    def validate_tags(cls, v):
        """Validate tags dictionary."""
        if v is not None:
            if len(v) > 10:
                raise ValueError("Maximum 10 tags allowed")
            for key, value in v.items():
                if len(key) > 50 or len(value) > 100:
                    raise ValueError("Tag keys max 50 chars, values max 100 chars")
        return v


class BulkSendEmailRequest(BaseModel):
    """Schema for sending emails to multiple recipients."""
    to: List[EmailStr] = Field(..., min_length=1, max_length=100, description="Recipient email addresses (max 100)")
    subject: str = Field(..., min_length=1, max_length=500, description="Email subject")
    html: str = Field(..., min_length=1, description="HTML email content")
    from_email: Optional[EmailStr] = Field(None, description="Sender email (defaults to config)")
    from_name: Optional[str] = Field(None, max_length=255, description="Sender name (defaults to config)")
    reply_to: Optional[EmailStr] = Field(None, description="Reply-to email address")
    workspace_id: Optional[str] = Field(None, description="Associated workspace ID")
    template_type: Optional[str] = Field(None, max_length=100, description="Email template type identifier")
    tags: Optional[Dict[str, str]] = Field(None, description="Custom tags for categorization")


class TestEmailRequest(BaseModel):
    """Schema for sending a test email."""
    to: EmailStr = Field(..., description="Test recipient email address")
    provider: Optional[str] = Field(None, description="Specific provider to use (resend, smtp, mock)")


class RetryEmailRequest(BaseModel):
    """Schema for retrying a failed email."""
    email_log_id: str = Field(..., description="Email log ID to retry")


class EmailQueryParams(BaseModel):
    """Schema for email query parameters."""
    workspace_id: Optional[str] = Field(None, description="Filter by workspace ID")
    user_id: Optional[str] = Field(None, description="Filter by user ID")
    status: Optional[str] = Field(None, description="Filter by status (queued, sent, failed, delivered, bounced)")
    template_type: Optional[str] = Field(None, description="Filter by template type")
    provider: Optional[str] = Field(None, description="Filter by provider (resend, smtp, mock)")
    from_date: Optional[datetime] = Field(None, description="Filter emails from this date")
    to_date: Optional[datetime] = Field(None, description="Filter emails until this date")
    limit: int = Field(50, ge=1, le=500, description="Maximum number of results (1-500)")
    offset: int = Field(0, ge=0, description="Pagination offset")


# ============================================================================
# Response Schemas
# ============================================================================

class EmailLogResponse(BaseModel):
    """Schema for email log response."""
    id: str
    workspace_id: Optional[str] = None
    user_id: Optional[str] = None
    template_type: Optional[str] = None
    provider: str
    provider_message_id: Optional[str] = None
    to_email: str
    from_email: str
    subject: str
    status: str
    error_message: Optional[str] = None
    sent_at: Optional[str] = None
    delivered_at: Optional[str] = None
    failed_at: Optional[str] = None
    tags: Optional[Dict[str, str]] = None
    created_at: str
    updated_at: str

    model_config = ConfigDict(from_attributes=True)


class SendEmailResponse(BaseModel):
    """Schema for send email response."""
    success: bool
    email_log_id: str
    status: str
    provider: str
    provider_message_id: Optional[str] = None
    message: str


class BulkSendEmailResult(BaseModel):
    """Result for a single email in bulk operation."""
    to: str
    success: bool
    email_log_id: Optional[str] = None
    status: Optional[str] = None
    error_message: Optional[str] = None


class BulkSendEmailResponse(BaseModel):
    """Schema for bulk email send response."""
    total_requested: int
    successful: int
    failed: int
    results: List[BulkSendEmailResult]


class EmailLogListResponse(BaseModel):
    """Schema for email log list response."""
    emails: List[EmailLogResponse]
    total_count: int
    limit: int
    offset: int
    has_more: bool


class EmailStatsResponse(BaseModel):
    """Schema for email statistics response."""
    total_sent: int
    total_failed: int
    total_delivered: int
    total_bounced: int
    success_rate: float
    provider_breakdown: Dict[str, int]
    template_breakdown: Dict[str, int]
    period_start: Optional[str] = None
    period_end: Optional[str] = None


class RetryEmailResponse(BaseModel):
    """Schema for retry email response."""
    success: bool
    email_log_id: str
    original_status: str
    new_status: str
    message: str


class TestEmailResponse(BaseModel):
    """Schema for test email response."""
    success: bool
    provider: str
    provider_message_id: Optional[str] = None
    message: str
    test_sent_to: str


# ============================================================================
# Internal/Utility Schemas
# ============================================================================

class EmailRecipientSchema(BaseModel):
    """Schema for email recipient."""
    email: EmailStr
    name: Optional[str] = None


class EmailMessageSchema(BaseModel):
    """Schema for complete email message structure."""
    to: List[EmailRecipientSchema]
    subject: str = Field(..., min_length=1, max_length=500)
    html: str = Field(..., min_length=1)
    from_email: EmailStr
    from_name: Optional[str] = None
    cc: Optional[List[EmailRecipientSchema]] = None
    bcc: Optional[List[EmailRecipientSchema]] = None
    reply_to: Optional[EmailStr] = None
    tags: Optional[Dict[str, str]] = None


class EmailProviderInfoResponse(BaseModel):
    """Schema for email provider information."""
    name: str
    is_primary: bool
    is_fallback: bool
    supports_webhooks: bool
    supports_tags: bool
    supports_cc_bcc: bool
    is_connected: bool


class EmailProvidersListResponse(BaseModel):
    """Schema for list of available email providers."""
    primary_provider: EmailProviderInfoResponse
    fallback_provider: Optional[EmailProviderInfoResponse] = None
    available_providers: List[str]


# ============================================================================
# Webhook Schemas (for Phase 4)
# ============================================================================

class EmailWebhookEvent(BaseModel):
    """Schema for email webhook event."""
    event_type: str = Field(..., description="Event type (delivered, bounced, complained, opened, clicked)")
    email_log_id: Optional[str] = None
    provider_message_id: str
    timestamp: datetime
    recipient_email: str
    metadata: Optional[Dict[str, str]] = None


class EmailWebhookResponse(BaseModel):
    """Schema for webhook processing response."""
    success: bool
    events_processed: int
    message: str
