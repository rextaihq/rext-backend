# Models are imported individually where needed
# This file intentionally left mostly empty to avoid circular import issues
# and to allow lazy loading of model relationships

from src.api.database.base import Base

# Core models
from src.api.models.workspace_models.workspace_model import WorkspaceModel
from src.api.models.workspace_models.workspace_integration import WorkspaceIntegration
from src.api.models.workspace_models.email_template import EmailTemplate
from src.api.models.user_models.users import Users

# Knowledge base models
from src.api.models.knowledge_models.knowledge_model import (
    BrandVoice,
    Website,
    KnowledgeFiles,
    TextKnowledge,
)
from src.api.models.knowledge_models.embedding_model import KnowledgeEmbedding
from src.api.models.content_models.content import Content
from src.api.models.content_models.content_seo_data import ContentSEOData
from src.api.models.knowledge_models.persona_model import Persona

# Admin models
from src.api.models.admin_models.admin_invitations import PlatformAdminInvitations

# Subscription models
from src.api.models.subscription_models.plans import SubscriptionPlan
from src.api.models.subscription_models.subscriptions import UserSubscription
from src.api.models.subscription_models.payment_methods import PaymentMethod

# Media models
from src.api.models.media_models.media import Media

# Notification models
from src.api.models.notification.notification_model import Notification


__all__ = [
    "Base",
    "WorkspaceModel",
    "WorkspaceIntegration",
    "EmailTemplate",
    "Users",
    "BrandVoice",
    "Website",
    "KnowledgeFiles",
    "TextKnowledge",
    "KnowledgeEmbedding",
    "Persona",
    "Content",
    "ContentSEOData",
    "SubscriptionPlan",
    "UserSubscription",
    "PaymentMethod",
    "Media",
    "Notification",
    "PlatformAdminInvitations",
]
