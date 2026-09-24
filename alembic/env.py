import asyncio
import os
import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import pool
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from alembic import context

# Add the src directory to Python path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))
from dotenv import load_dotenv

load_dotenv()

load_dotenv()

# Import SQLAlchemy Base and all models — these are required by Alembic
# autogenerate even though they appear unused (they register on Base.metadata)
from src.api.database.base import Base  # noqa: E402, F401
from src.api.models.admin_models import (  # noqa: E402, F401
    AccountCreationIpAllowlist,
    ApiUsageHourly,
    ApiUsageRollupState,
    CustomerNote,
    ErrorLog,
    PlatformAdminInvitations,
)
from src.api.models.audit_models.audit_logs import AuditLog  # noqa: E402, F401
from src.api.models.content_models import Content, ContentSEOData  # noqa: E402, F401
from src.api.models.email_models import EmailEvent, EmailLog  # noqa: E402, F401
from src.api.models.integrations.shopify_app_install import (  # noqa: E402
    ShopifyAppInstall,  # noqa: F401
)
from src.api.models.knowledge_models.knowledge_model import (  # noqa: E402, F401
    BrandVoice,
    KnowledgeFiles,
    TextKnowledge,
    Website,
)
from src.api.models.knowledge_models.persona_model import Persona  # noqa: E402, F401
from src.api.models.notification.notification_model import Notification  # noqa: E402, F401
from src.api.models.subscription_models import (  # noqa: E402, F401
    DiscountUsage,
    License,
    LicenseActivation,
    PaymentMethod,
    Refund,
    SubscriptionPlan,
    TrialConversion,
    UserSubscription,
    WebhookEvent,
)
from src.api.models.user_models import (  # noqa: E402, F401
    AccountRecoveryRequest,
    EmailPreferences,
    NotificationPreferences,
    OAuthAccount,
    Permission,
    Role,
    RolePermission,
    TokenBlacklist,
    UserInvitations,
    UserOnboarding,
    UserPreferences,
    UserRole,
    Users,
    UserSession,
)
from src.api.models.user_models.impersonation_session import (  # noqa: E402
    ImpersonationSession,  # noqa: F401
)
from src.api.models.workspace_models.email_template import EmailTemplate  # noqa: E402, F401
from src.api.models.workspace_models.workspace_integration import (  # noqa: E402
    WorkspaceIntegration,  # noqa: F401
)

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
    # Parse and clean URL for asyncpg
    url_obj = make_url(get_url())
    query_dict = dict(url_obj.query)

    # Remove unsupported params like sslmode
    query_dict.pop("sslmode", None)
    query_dict.pop("channel_binding", None)

    # Rebuild URL safely
    clean_url = url_obj._replace(query=query_dict)

    connectable = create_async_engine(
        clean_url,
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
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
