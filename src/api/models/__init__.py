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

# Brand voice and persona models
from src.api.models.knowledge_models.knowledge_model import BrandVoice
from src.api.models.knowledge_models.persona_model import Persona

# Notification models
from src.api.models.notification.notification_model import Notification
from src.api.models.subscription_models.payment_methods import PaymentMethod

# Subscription models
from src.api.models.subscription_models.plans import SubscriptionPlan
from src.api.models.subscription_models.subscriptions import UserSubscription
from src.api.models.user_models.users import Users

# Core models
from src.api.models.workspace_models.workspace_member import WorkspaceMembers
from src.api.models.workspace_models.workspace_model import WorkspaceModel

# WorkspaceMembers is imported for its side effect as much as for export:
# UserInvitations.workspace_members names it as a string ("WorkspaceMembers"),
# and SQLAlchemy resolves such names against the class registry the first time
# any query configures mappers. Until something imported this module, that name
# resolved to nothing and the FIRST ORM query in the process — whichever
# endpoint happened to run first, in practice /user/refresh — failed with
# "failed to locate a name ('WorkspaceMembers')" and returned 500.

__all__ = [
    "Base",
    "WorkspaceModel",
    "WorkspaceMembers",
    "WorkspaceIntegration",
    "ShopifyAppInstall",
    "Users",
    "BrandVoice",
    "Persona",
    "Content",
    "ContentSEOData",
    "SubscriptionPlan",
    "UserSubscription",
    "PaymentMethod",
    "Notification",
    "PlatformAdminInvitations",
]
