"""
Webhook Schemas for Email Events

Pydantic models for validating Resend webhook payloads.
Based on Resend webhook documentation:
https://resend.com/docs/api-reference/webhooks/event-types
"""
from pydantic import BaseModel, Field, EmailStr
from typing import Literal, Optional, Dict, Any
from datetime import datetime, timezone


class WebhookEmailData(BaseModel):
    """Email data embedded in webhook payload"""
    from_: EmailStr = Field(..., alias="from")
    to: list[EmailStr]
    subject: str
    created_at: datetime


class WebhookEventPayload(BaseModel):
    """
    Resend webhook event payload structure.

    Common fields across all event types:
    - type: Event type (delivered, opened, clicked, etc.)
    - created_at: When event occurred (ISO 8601 timestamp)
    - data: Event-specific data
    """
    type: Literal[
        "email.sent",
        "email.delivered",
        "email.delivery_delayed",
        "email.bounced",
        "email.complained",
        "email.opened",
        "email.clicked"
    ] = Field(..., description="Type of email event")

    created_at: str = Field(..., description="ISO 8601 timestamp of event")

    data: Dict[str, Any] = Field(..., description="Event-specific data")


class ResendWebhookRequest(BaseModel):
    """
    Full Resend webhook request payload.

    Includes event data plus metadata for processing.
    """
    type: str = Field(..., description="Event type")
    created_at: str = Field(..., description="Event timestamp")
    data: Dict[str, Any] = Field(..., description="Event payload")

    class Config:
        # Allow extra fields for forward compatibility
        extra = "allow"


class WebhookProcessingResult(BaseModel):
    """Result of webhook processing"""
    success: bool
    event_id: Optional[str] = None
    email_log_id: Optional[str] = None
    message: str
    event_type: Optional[str] = None


class WebhookResponse(BaseModel):
    """Response sent back to Resend after processing webhook"""
    status: Literal["ok", "error"] = "ok"
    message: str = "Webhook received"
    event_id: Optional[str] = None


# Event-specific payload models for type safety

class DeliveredEventData(BaseModel):
    """Data for email.delivered event"""
    email_id: str = Field(..., description="Resend email ID")
    from_: EmailStr = Field(..., alias="from")
    to: list[EmailStr]
    subject: str
    created_at: str


class BouncedEventData(BaseModel):
    """Data for email.bounced event"""
    email_id: str
    from_: EmailStr = Field(..., alias="from")
    to: list[EmailStr]
    subject: str
    created_at: str
    bounce_type: Optional[str] = None  # "hard" or "soft"
    bounce_reason: Optional[str] = None


class ComplainedEventData(BaseModel):
    """Data for email.complained event (spam report)"""
    email_id: str
    from_: EmailStr = Field(..., alias="from")
    to: list[EmailStr]
    subject: str
    created_at: str
    complaint_feedback_type: Optional[str] = None


class OpenedEventData(BaseModel):
    """Data for email.opened event"""
    email_id: str
    from_: EmailStr = Field(..., alias="from")
    to: list[EmailStr]
    subject: str
    created_at: str
    opened_at: Optional[str] = None


class ClickedEventData(BaseModel):
    """Data for email.clicked event"""
    email_id: str
    from_: EmailStr = Field(..., alias="from")
    to: list[EmailStr]
    subject: str
    created_at: str
    clicked_at: Optional[str] = None
    link: Optional[str] = None  # URL that was clicked
