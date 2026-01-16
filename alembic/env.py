from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import context

import os
import sys
import asyncio
from pathlib import Path

# Add the src directory to Python path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from dotenv import load_dotenv
load_dotenv()

# Import SQLAlchemy Base and all models
from src.api.database.base import Base
from src.api.models.user_models.users import Users
from src.api.models.user_models.roles import Role
from src.api.models.user_models.permissions import Permission
from src.api.models.user_models.user_roles import UserRole
from src.api.models.user_models.role_permissions import RolePermission
from src.api.models.user_models.invitations import UserInvitations
from src.api.models.user_models.token_blacklist import TokenBlacklist
from src.api.models.user_models.notification_preferences import NotificationPreferences
from src.api.models.workspace_models.workspace_model import WorkspaceModel
from src.api.models.workspace_models.workspace_member import WorkspaceMembers
from src.api.models.knowledge_models.knowledge_model import (
    BrandVoice, Website, KnowledgeFiles, TextKnowledge
)
from src.api.models.subscription_models import (
    SubscriptionPlan, UserSubscription, PaymentMethod, WebhookEvent,
    License, LicenseActivation, DiscountUsage, TrialConversion, Refund
)
from src.api.models.audit_models.audit_logs import AuditLog
from src.api.models.content_models import (
    Content, ContentProgress, ContentSEOData, ContentReview, 
    ContentVersion, ConnectedSite, ContentMedia
)
from src.api.models.admin_models import (
    CustomerNote, ErrorLog, PlatformAdminInvitations
)
from src.api.models.user_models import (
    Users, Role, Permission, UserRole, RolePermission, 
    UserInvitations, TokenBlacklist, NotificationPreferences,
    UserSession, OAuthAccount, UserOnboarding, EmailPreferences,
    UserPreferences
)
from src.api.models.user_models.impersonation_session import ImpersonationSession
from src.api.models.media_models.media import Media
from src.api.models.knowledge_models.persona_model import Persona
from src.api.models.notification.notification_model import Notification
from src.api.models.workspace_models.email_template import EmailTemplate
from src.api.models.email_models import EmailLog, EmailEvent

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def get_url():
    """Get database URL from environment variable."""
    url = os.getenv("POSTGRES_URI_CUSTOM")
    if not url:
        raise ValueError("POSTGRES_URI_CUSTOM environment variable not set")
    # For alembic async migrations, use asyncpg driver
    if url.startswith("postgresql://") and "+asyncpg" not in url:
        url = url.replace("postgresql://", "postgresql+asyncpg://")
    return url


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations in 'online' mode with async engine."""
    connectable = create_async_engine(
        get_url(),
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def do_run_migrations(connection):
    """Execute migrations with the provided connection."""
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode using asyncio."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
