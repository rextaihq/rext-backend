# Models are imported individually where needed
# This file intentionally left mostly empty to avoid circular import issues
# and to allow lazy loading of model relationships

from src.api.database.base import Base

# Admin models
from src.api.models.admin_models.admin_invitations import PlatformAdminInvitations
from src.api.models.content_models.content import Content
from src.api.models.content_models.content_seo_data import ContentSEOData
from src.api.models.integrations.shopify_app_install import ShopifyAppInstall
from src.api.models.integrations.workspace_integration import WorkspaceIntegration

# Knowledge base models
from src.api.models.knowledge_models.knowledge_model import (
    BrandVoice,
    KnowledgeFiles,
    TextKnowledge,
    Website,
)
from src.api.models.knowledge_models.persona_model import Persona

# Notification models
from src.api.models.notification.notification_model import Notification
from src.api.models.subscription_models.payment_methods import PaymentMethod

# Subscription models
from src.api.models.subscription_models.plans import SubscriptionPlan
from src.api.models.subscription_models.subscriptions import UserSubscription
from src.api.models.user_models.users import Users
from src.api.models.workspace_models.email_template import EmailTemplate

# Core models
from src.api.models.workspace_models.workspace_model import WorkspaceModel

__all__ = [
    "Base",
    "WorkspaceModel",
    "WorkspaceIntegration",
    "ShopifyAppInstall",
    "EmailTemplate",
    "Users",
    "BrandVoice",
    "Website",
    "KnowledgeFiles",
    "TextKnowledge",
    "Persona",
    "Content",
    "ContentSEOData",
    "SubscriptionPlan",
    "UserSubscription",
    "PaymentMethod",
    "Notification",
    "PlatformAdminInvitations",
]
