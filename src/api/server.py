# Standard library imports
import os
from typing import Union
from contextlib import asynccontextmanager
import src.api.models
from src.api.models.user_models.invitations import UserInvitations
from src.api.models.user_models.role_permissions import RolePermission
from src.api.models.user_models.roles import Role
from src.api.models.user_models.user_roles import UserRole
from src.api.models.user_models.permissions import Permission
from src.api.models.subscription_models.plans import SubscriptionPlan
from src.api.models.subscription_models.subscriptions import UserSubscription
# Third-party imports
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

# Local application imports
from src.api.routes.users import router as users_router
from src.api.routes.topics.topic_generation_route import router as topic_router
from src.api.routes.workspaces import router as workspace_router, workspaces_router
from src.api.routes.workspaces.workspace_knowledge import router as workspace_knowledge_router
from src.api.routes.workspaces.workspace_knowledge_bases import router as workspace_knowledge_bases_router
from src.api.routes.workspaces.email_template_route import router as email_template_router
from src.api.routes.content.modules import router as content_router
from src.api.routes.roles.modules import router as roles_router
from src.api.routes.permissions.modules import router as permissions_router
from src.api.routes.subscriptions.plan_routes import router as plan_routes_router
from src.api.routes.subscriptions.subscription_routes import router as subscription_routes_router
from src.api.routes.subscriptions.checkout_routes import router as checkout_routes_router
from src.api.routes.subscriptions.webhook_routes import router as webhook_routes_router
from src.api.routes.subscriptions.admin import router as admin_subscription_routes_router
from src.api.routes.audit.modules import router as audit_router
from src.api.routes.security.security_routes import router as security_router
from src.api.routes.events import router as events_router
# Email routes (Phase 3 complete - Python-based templates)
from src.api.routes.email import preview_router, webhook_router
from src.api.routes.users.email_preferences import router as email_prefs_router
from src.api.database.database import engine

# Middleware imports
from src.api.middleware.request_tracker import RequestTrackerMiddleware
from src.api.middleware.error_handler import ErrorHandlerMiddleware, setup_exception_handlers
from src.api.middleware.security import SecurityHeadersMiddleware
from src.api.middleware.rate_limiter import RateLimiterMiddleware
from src.api.config import settings
from src.utils.response_utils import success
from src.utils.logger import logger

# Structured logging
from src.api.lib.logging_config import configure_logging, RequestIDMiddleware

# Prompts
from src.flow.prompts.prompt_manager import PromptManager

load_dotenv()

# Configure structured logging at startup
configure_logging()

DB_URI = os.getenv("POSTGRES_URI_CUSTOM")

# Database tables are managed by Alembic migrations
# Run migrations with: alembic upgrade head


def check_migrations():
    """Check if database migrations are up to date."""
    try:
        from alembic.config import Config
        from alembic.script import ScriptDirectory
        from alembic.runtime.migration import MigrationContext

        alembic_cfg = Config("alembic.ini")
        script = ScriptDirectory.from_config(alembic_cfg)

        with engine.begin() as connection:
            context = MigrationContext.configure(connection)
            current_rev = context.get_current_revision()
            head_rev = script.get_current_head()

            if current_rev != head_rev:
                logger.warning(
                    f"Database migration out of date. "
                    f"Current: {current_rev}, Expected: {head_rev}. "
                    f"Run 'alembic upgrade head' to update."
                )
                return False
            logger.info(f"Database migrations up to date (revision: {current_rev})")
            return True
    except Exception as e:
        logger.error(f"Error checking migrations: {e}")
        return False


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    # Startup
    logger.info("Starting Wrext API server...")
    logger.info(f"Environment: {settings.ENVIRONMENT}")
    logger.info(f"Database URI: {DB_URI[:20]}..." if DB_URI else "No database URI configured")
    logger.info("Database managed by Alembic migrations")
    logger.info("Middleware configured: RequestTracker, ErrorHandler, SecurityHeaders")
    logger.info(f"CORS allowed origins: {settings.allowed_origins_list}")
    logger.info("Registering Prompt")
    PromptManager(auto_register=False)  
    logger.info("✅ Prompts initialized successfully")

    # Optional: Check migration status (uncomment to enable)
    # check_migrations()

    yield
    # Shutdown
    logger.info("Shutting down Wrext API server...")

app = FastAPI(
    title="Wrext Content Automation API",
    version="1.0.0",
    description="API for managing content automation workflows with consistent response handling",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)

# ============================================================================
# MIDDLEWARE CONFIGURATION
# ============================================================================

# Request tracking middleware (first in chain)
app.add_middleware(
    RequestTrackerMiddleware,
    header_name="X-Request-ID",
    generate_if_missing=True,
    log_requests=True,
    include_processing_time=True
)

# Structured logging request ID middleware
app.add_middleware(RequestIDMiddleware)

# Error handling middleware (second in chain)
app.add_middleware(
    ErrorHandlerMiddleware,
    include_debug_info=os.getenv("DEBUG", "false").lower() == "true",
    log_full_traceback=True,
    filter_sensitive_data=True,
    max_error_details=10
)

# CORS middleware - configured via environment variables
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "Content-Type"],
    max_age=3600,  # Cache preflight requests for 1 hour
)

# Security headers middleware
app.add_middleware(SecurityHeadersMiddleware)

# Rate limiting middleware - protects against API abuse and DDoS
app.add_middleware(
    RateLimiterMiddleware,
    requests_per_minute=int(os.getenv("RATE_LIMIT_PER_MINUTE", "100")),
    requests_per_hour=int(os.getenv("RATE_LIMIT_PER_HOUR", "1000")),
    requests_per_day=int(os.getenv("RATE_LIMIT_PER_DAY", "10000")),
    enable=os.getenv("RATE_LIMITING_ENABLED", "true").lower() == "true"
)

# Setup global exception handlers
setup_exception_handlers(app)

# ============================================================================
# ROUTE REGISTRATION
# ============================================================================

# Include all API routes with consistent prefix (/api/v1)
app.include_router(users_router, prefix="/api/v1", tags=["Authentication"])
app.include_router(topic_router, prefix="/api/v1", tags=["Topic Generation"])
app.include_router(workspace_router, prefix="/api/v1", tags=["Workspaces"])
app.include_router(workspaces_router, prefix="/api/v1", tags=["Workspaces"])  # Alias for frontend compatibility
app.include_router(workspace_knowledge_router, prefix="/api/v1", tags=["Workspace Knowledge"])
app.include_router(workspace_knowledge_bases_router, prefix="/api/v1", tags=["Knowledge Bases"])
app.include_router(events_router, prefix="/api/v1", tags=["Events"])
app.include_router(email_template_router, prefix="/api/v1", tags=["Email Templates"])
app.include_router(content_router, prefix="/api/v1", tags=["Content"])
app.include_router(roles_router, prefix="/api/v1", tags=["Roles"])
app.include_router(permissions_router, prefix="/api/v1", tags=["Permissions"])
app.include_router(plan_routes_router, prefix="/api/v1", tags=["Subscription Plans"])
app.include_router(subscription_routes_router, prefix="/api/v1", tags=["Subscriptions"])
app.include_router(checkout_routes_router, prefix="/api/v1", tags=["Subscriptions", "Checkout"])
app.include_router(webhook_routes_router, prefix="/api/v1", tags=["Subscriptions", "Webhooks"])
app.include_router(admin_subscription_routes_router, prefix="/api/v1")
app.include_router(audit_router, prefix="/api/v1", tags=["Audit Logs"])
app.include_router(security_router, prefix="/api/v1", tags=["Security Monitoring"])
# Email routes (Phase 3 complete - Python-based templates)
app.include_router(preview_router, prefix="/api/v1/email", tags=["Email Preview"])
app.include_router(webhook_router, prefix="/api/v1/email", tags=["Email Webhooks"])
app.include_router(email_prefs_router, prefix="/api/v1", tags=["Email Preferences"])

# ============================================================================
# ROOT ENDPOINTS
# ============================================================================

@app.get("/", tags=["Health"])
def read_root(request: Request):
    """Root endpoint with API information."""
    return success(
        data={
            "service": "Wrext Content Automation API",
            "version": "1.0.0",
            "status": "operational",
            "docs_url": "/docs",
            "redoc_url": "/redoc",
            "openapi_url": "/openapi.json"
        },
        request=request,
        message="Welcome to Wrext Content Automation API"
    )


@app.get("/health", tags=["Health"])
def health_check(request: Request):
    """Health check endpoint for monitoring."""
    return success(
        data={
            "status": "healthy",
            "service": "wrext-api",
            "version": "1.0.0",
            "database": "connected" if DB_URI else "not_configured",
            "environment": os.getenv("ENVIRONMENT", "development")
        },
        request=request,
        message="Service is healthy"
    )


@app.get("/api/status", tags=["Health"])
def api_status(request: Request):
    """API status endpoint with detailed information."""
    return success(
        data={
            "api_status": "operational",
            "endpoints": {
                "authentication": "/api/v1/user",
                "topics": "/api/v1/topic",
                "workspaces": "/api/v1/workspace",
                "content": "/api/v1/content",
                "knowledge": "/api/v1/knowledge"
            },
            "features": {
                "consistent_responses": True,
                "error_tracking": True,
                "request_correlation": True,
                "comprehensive_logging": True
            }
        },
        request=request,
        message="API is operational with all features enabled"
    )


# ============================================================================
# APPLICATION STARTUP
# ============================================================================

if __name__ == "__main__":
    import uvicorn

    # Get configuration from environment
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    debug = os.getenv("DEBUG", "false").lower() == "true"

    logger.info(f"Starting server on {host}:{port} (debug={debug})")

    uvicorn.run(
        app,
        host=host,
        port=port,
        reload=debug,
        access_log=True,
        log_level="info" if not debug else "debug"
    )
