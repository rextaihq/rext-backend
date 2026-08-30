from pydantic import BaseModel
from typing import Dict, Optional

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

class EmailPreferencesResponse(BaseModel):
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

class UnsubscribeResponse(BaseModel):
    unsubscribed_from: str
