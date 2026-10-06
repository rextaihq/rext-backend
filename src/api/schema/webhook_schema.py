"""
Webhook Schemas for Email Events

Pydantic models for validating Resend webhook payloads.
Based on Resend webhook documentation:
https://resend.com/docs/api-reference/webhooks/event-types
"""

from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class ResendWebhookRequest(BaseModel):
    """
    Full Resend webhook request payload.

    Includes event data plus metadata for processing.
    """

    type: str = Field(..., description="Event type")
    created_at: str = Field(..., description="Event timestamp")
    data: Dict[str, Any] = Field(..., description="Event payload")

    # Allow extra fields for forward compatibility
    model_config = ConfigDict(extra="allow")


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
