from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class WorkspaceNotifications(BaseModel):
    invite_received: bool
    invite_accepted: bool
    role_changed: bool
    member_removed: bool

class ContentGenerationNotifications(BaseModel):
    generation_started: bool
    generation_completed: bool
    generation_failed: bool
    content_published: bool

class BillingNotifications(BaseModel):
    payment_success: bool
    payment_failed: bool
    subscription_cancelled: bool
    subscription_expiring: bool
    trial_ending: bool
    usage_limit_warning: bool
    usage_limit_exceeded: bool

class KnowledgeBaseNotifications(BaseModel):
    processing_completed: bool
    processing_failed: bool

class MarketingNotifications(BaseModel):
    marketing_updates: bool

class NotificationPreferencesResponse(BaseModel):
    """Response schema for notification preferences matching the model's to_dict() output."""
    email_enabled: bool
    in_app_enabled: bool
    digest_enabled: bool
    digest_frequency: str
    digest_last_sent_at: Optional[str] = None
    workspace_notifications: WorkspaceNotifications
    content_generation: ContentGenerationNotifications
    billing: BillingNotifications
    knowledge_base: KnowledgeBaseNotifications
    marketing: MarketingNotifications

class UpdateNotificationPreferencesRequest(BaseModel):
    """Request schema for updating notification preferences.
    Supports partial updates - all fields are optional.
    """
    # GLOBAL
    email_enabled: Optional[bool] = Field(None, alias="email_notifications")
    in_app_enabled: Optional[bool] = Field(None, alias="in_app_notifications")

    # WORKSPACE
    ws_invite_received: Optional[bool] = None
    ws_invite_accepted: Optional[bool] = None
    ws_role_changed: Optional[bool] = None
    ws_member_removed: Optional[bool] = None

    # CONTENT GENERATION
    gen_started: Optional[bool] = None
    gen_completed: Optional[bool] = None
    gen_failed: Optional[bool] = None
    gen_published: Optional[bool] = None

    # BILLING
    billing_payment_success: Optional[bool] = None
    billing_payment_failed: Optional[bool] = None
    billing_subscription_cancelled: Optional[bool] = None
    billing_subscription_expiring: Optional[bool] = None
    billing_trial_ending: Optional[bool] = None
    billing_usage_limit_warning: Optional[bool] = None
    billing_usage_limit_exceeded: Optional[bool] = None

    # KNOWLEDGE BASE
    kb_processing_completed: Optional[bool] = None
    kb_processing_failed: Optional[bool] = None

    # DIGEST
    digest_enabled: Optional[bool] = None
    digest_frequency: Optional[Literal["daily", "weekly", "monthly"]] = None

    # MARKETING
    marketing_updates: Optional[bool] = None

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)