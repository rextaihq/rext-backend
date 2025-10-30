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
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

# Local application imports
from src.api.routes.users import router as users_router
from src.api.routes.health import router as health_router
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
from src.api.routes.subscriptions.license_routes import router as license_routes_router
from src.api.routes.subscriptions.trial_routes import router as trial_routes_router
from src.api.routes.subscriptions.admin import router as admin_subscription_routes_router
from src.api.routes.admin.customer_routes import router as admin_customer_routes_router
from src.api.routes.admin.monitoring_routes import router as admin_monitoring_routes_router
from src.api.routes.admin.reports_routes import router as admin_reports_routes_router
from src.api.routes.admin.email_analytics_routes import router as admin_email_analytics_routes_router
from src.api.routes.admin.email_admin_routes import router as admin_email_routes_router
from src.api.routes.admin.webhook_monitoring_routes import router as admin_webhook_monitoring_routes_router
from src.api.routes.admin.export_routes import router as admin_export_routes_router
from src.api.routes.admin.admin_invitation_routes import admin_router as admin_invitation_admin_router
from src.api.routes.admin.admin_invitation_routes import public_router as admin_invitation_public_router
from src.api.routes.admin.invitation_analytics_routes import router as invitation_analytics_router
from src.api.routes.audit.modules import router as audit_router
from src.api.routes.security.security_routes import router as security_router
from src.api.routes.events import router as events_router
# Email routes (Phase 3 complete - Python-based templates)
from src.api.routes.email import preview_router, webhook_router
from src.api.routes.users.email_preferences import router as email_prefs_router
from src.api.routes.users.onboarding import router as onboarding_router
from src.api.routes.media import router as media_router
from src.api.routes.invitations import router as invitations_router
from src.api.database.async_database import async_engine
from src.api.database.base import Base
from src.api.database.async_database import async_engine
# Middleware imports
from src.api.middleware.request_tracker import RequestTrackerMiddleware
from src.api.middleware.error_handler import ErrorHandlerMiddleware, setup_exception_handlers
from src.api.middleware.security import SecurityHeadersMiddleware
from src.api.middleware.rate_limiter import RateLimiterMiddleware
from src.config.payment_config import payment_settings
from src.tasks.scheduled_tasks import start_scheduled_tasks, shutdown_scheduled_tasks
from src.api.cache.redis_client import cache
from src.api.config import settings
from src.utils.response_utils import success
from src.utils.logger import logger

# Structured logging
from src.api.lib.logging_config import configure_logging, RequestIDMiddleware

# Sentry error monitoring
from src.api.lib.sentry_config import init_sentry

# Prompts
from src.flow.prompts.prompt_manager import PromptManager

load_dotenv()

# Configure structured logging at startup
configure_logging()

DB_URI = settings.POSTGRES_URI_CUSTOM

# Database tables are managed by Alembic migrations
# Run migrations with: alembic upgrade head


async def check_migrations():
    """Check if database migrations are up to date."""
    try:
        from alembic.config import Config
        from alembic.script import ScriptDirectory
        from alembic.runtime.migration import MigrationContext

        alembic_cfg = Config("alembic.ini")
        script = ScriptDirectory.from_config(alembic_cfg)

        # Use run_sync to execute sync Alembic code with async engine
        def do_check(connection):
            context = MigrationContext.configure(connection)
            return context.get_current_revision()

        async with async_engine.begin() as connection:
            current_rev = await connection.run_sync(do_check)
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
async def lifespan(app):
    """
    Application startup and shutdown lifecycle.
    Ensures database tables exist, Redis is connected,
    Sentry and tasks are initialized cleanly.
    """
    logger.info("🚀 Starting Wrext API server...")
    logger.info(f"Environment: {settings.ENVIRONMENT}")

    # --- Initialize Sentry ---
    try:
        init_sentry(settings)
        logger.info("✅ Sentry initialized successfully")
    except Exception as e:
        logger.warning(f"⚠️ Failed to initialize Sentry: {e}")

    # --- Ensure database tables exist ---
    try:
        async with async_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("✅ Verified database tables exist or created if missing")
    except Exception as e:
        logger.error(f"❌ Failed to verify/create database tables: {e}")

    # --- Connect Redis cache ---
    try:
        await cache.connect()
        logger.info("✅ Redis cache connected")
    except Exception as e:
        logger.error(f"❌ Failed to connect to Redis: {e}")

    # --- Validate production configuration ---
    if settings.ENVIRONMENT == "production":
        try:
            if payment_settings.payment_provider in ["lemonsqueezy", "lemonsqueezy_sandbox"]:
                if not payment_settings.lemonsqueezy_webhook_secret:
                    raise RuntimeError("Missing LEMONSQUEEZY_WEBHOOK_SECRET in production")
                if not payment_settings.lemonsqueezy_api_key:
                    raise RuntimeError("Missing LEMONSQUEEZY_API_KEY in production")
                if not payment_settings.lemonsqueezy_store_id:
                    raise RuntimeError("Missing LEMONSQUEEZY_STORE_ID in production")
                logger.info("✅ LemonSqueezy configuration validated")
        except Exception as e:
            logger.critical(f"🚨 Invalid production config: {e}")
            raise

    # --- Initialize prompt system ---
    try:
        PromptManager(auto_register=False)
        logger.info("✅ Prompts initialized successfully")
    except Exception as e:
        logger.warning(f"⚠️ Failed to initialize PromptManager: {e}")

    # --- Start background scheduled tasks ---
    try:
        start_scheduled_tasks()
        logger.info("✅ Scheduled tasks started")
    except Exception as e:
        logger.warning(f"⚠️ Failed to start scheduled tasks: {e}")

    # --- Application is now ready ---
    logger.info("✅ Application startup complete. Ready to serve requests.")
    yield

    # --- Graceful shutdown ---
    logger.info("🛑 Shutting down application...")

    try:
        shutdown_scheduled_tasks()
        logger.info("✅ Scheduled tasks stopped")
    except Exception as e:
        logger.warning(f"⚠️ Failed to stop scheduled tasks: {e}")

    try:
        await cache.disconnect()
        logger.info("✅ Redis cache disconnected")
    except Exception as e:
        logger.warning(f"⚠️ Failed to disconnect Redis: {e}")

    logger.info("👋 Application shutdown complete.")

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

# Sentry user context middleware (enrich errors with user info)
from src.api.middleware.sentry_middleware import SentryUserContextMiddleware
app.add_middleware(SentryUserContextMiddleware)

# Error handling middleware (second in chain)
app.add_middleware(
    ErrorHandlerMiddleware,
    include_debug_info=settings.DEBUG,
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
    requests_per_minute=settings.RATE_LIMIT_PER_MINUTE,
    requests_per_hour=settings.RATE_LIMIT_PER_HOUR,
    requests_per_day=settings.RATE_LIMIT_PER_DAY,
    enable=settings.RATE_LIMITING_ENABLED
)

# Setup global exception handlers
setup_exception_handlers(app)

# ============================================================================
# ROUTE REGISTRATION
# ============================================================================

# Include all API routes with consistent prefix (/api/v1)
app.include_router(users_router, prefix="/api/v1", tags=["Authentication"])
app.include_router(health_router, prefix="/api/v1", tags=["Health"])
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
app.include_router(license_routes_router, prefix="/api/v1", tags=["Licenses"])
app.include_router(trial_routes_router, prefix="/api/v1", tags=["Trials"])
app.include_router(admin_subscription_routes_router, prefix="/api/v1")
app.include_router(admin_customer_routes_router, prefix="/api/v1/admin", tags=["Admin - Customers"])
app.include_router(admin_monitoring_routes_router, prefix="/api/v1/admin", tags=["Admin - Monitoring"])
app.include_router(admin_reports_routes_router, prefix="/api/v1/admin", tags=["Admin - Reports"])
app.include_router(admin_email_analytics_routes_router, prefix="/api/v1", tags=["Admin - Email Analytics"])
app.include_router(admin_email_routes_router)  # Prefix already defined in router
app.include_router(admin_webhook_monitoring_routes_router, prefix="/api/v1/admin", tags=["Admin - Webhooks"])
app.include_router(admin_export_routes_router, prefix="/api/v1/admin", tags=["Admin - Exports"])
app.include_router(admin_invitation_admin_router, prefix="/api/v1", tags=["Admin - Platform Invitations"])
app.include_router(admin_invitation_public_router, prefix="/api/v1", tags=["Public - Admin Invitations"])
app.include_router(invitation_analytics_router, prefix="/api/v1/admin/analytics", tags=["Admin - Invitation Analytics"])
app.include_router(audit_router, prefix="/api/v1", tags=["Audit Logs"])
app.include_router(security_router, prefix="/api/v1", tags=["Security Monitoring"])
# Email routes (Phase 3 complete - Python-based templates)
app.include_router(preview_router, prefix="/api/v1/email", tags=["Email Preview"])
app.include_router(webhook_router, prefix="/api/v1/email", tags=["Email Webhooks"])
app.include_router(email_prefs_router, prefix="/api/v1", tags=["Email Preferences"])
# Onboarding routes (Phase 9)
app.include_router(onboarding_router, prefix="/api/v1", tags=["Onboarding"])
# Media routes
app.include_router(media_router, prefix="/api/v1", tags=["Media"])
# Public invitation routes (validate and accept)
app.include_router(invitations_router, prefix="/api/v1", tags=["Invitations"])

# ============================================================================
# STATIC FILE SERVING
# ============================================================================

# Mount media directory for serving uploaded files
# This allows the frontend to access media files via URLs like:
# http://localhost:2024/media/workspace-id/user-id/filename.jpg
media_dir = os.path.join(os.getcwd(), "media")
if not os.path.exists(media_dir):
    os.makedirs(media_dir, exist_ok=True)
    logger.info(f"Created media directory at: {media_dir}")

app.mount("/media", StaticFiles(directory=media_dir), name="media")
logger.info(f"Mounted media directory for static file serving: {media_dir}")

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
async def health_check(request: Request):
    """
    Comprehensive health check endpoint for monitoring.

    Returns overall system health with detailed dependency checks.
    Returns 200 if healthy, 503 if degraded.
    """
    from datetime import datetime
    from fastapi.responses import JSONResponse
    from sqlalchemy import text
    import shutil

    status = {
        "status": "healthy",
        "service": "wrext-api",
        "version": "1.0.0",
        "environment": settings.ENVIRONMENT,
        "timestamp": datetime.utcnow().isoformat(),
        "checks": {}
    }

    # Database check
    try:
        from src.api.database.async_database import get_async_db_context
        async with get_async_db_context() as db:
            await db.execute(text("SELECT 1"))
            status["checks"]["database"] = "healthy"
    except Exception as e:
        status["checks"]["database"] = f"unhealthy: {str(e)}"
        status["status"] = "degraded"

    # Redis check (optional - graceful degradation)
    try:
        from src.api.cache.redis_client import cache
        if cache.redis is not None:
            await cache.redis.ping()
            status["checks"]["redis"] = "healthy"
        else:
            status["checks"]["redis"] = "not_configured"
    except ImportError:
        status["checks"]["redis"] = "not_configured"
    except Exception as e:
        status["checks"]["redis"] = f"unhealthy: {str(e)}"
        # Don't mark overall status as degraded - cache is optional

    # Disk space check
    try:
        disk = shutil.disk_usage("/")
        disk_percent = (disk.used / disk.total) * 100
        status["checks"]["disk_space"] = {
            "percent_used": round(disk_percent, 2),
            "status": "healthy" if disk_percent < 90 else "warning"
        }
        if disk_percent >= 95:
            status["status"] = "degraded"
    except Exception as e:
        status["checks"]["disk_space"] = f"error: {str(e)}"

    # OpenAI check (optional - non-blocking)
    try:
        import httpx
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}"},
                timeout=5.0
            )
            status["checks"]["openai"] = "healthy" if response.status_code == 200 else "degraded"
    except Exception:
        status["checks"]["openai"] = "unavailable"
        # Don't mark overall status as degraded for external service

    # Return appropriate status code
    status_code = 200 if status["status"] == "healthy" else 503
    return JSONResponse(content=status, status_code=status_code)


@app.get("/health/live", tags=["Health"])
async def liveness_check(request: Request):
    """
    Kubernetes liveness probe endpoint.

    Returns 200 if the application is running (even if dependencies are unavailable).
    This endpoint should only fail if the application has crashed or is deadlocked.
    Kubernetes will restart the pod if this returns non-200.
    """
    from datetime import datetime
    return {
        "status": "alive",
        "service": "wrext-api",
        "timestamp": datetime.utcnow().isoformat()
    }


@app.get("/health/ready", tags=["Health"])
async def readiness_check(request: Request):
    """
    Kubernetes readiness probe endpoint.

    Returns 200 if the application can accept traffic (all critical dependencies available).
    Returns 503 if dependencies are unavailable.
    Kubernetes will remove pod from load balancer if this returns non-200.
    """
    from datetime import datetime
    from fastapi.responses import JSONResponse
    from sqlalchemy import text

    status = {
        "status": "ready",
        "service": "wrext-api",
        "timestamp": datetime.utcnow().isoformat(),
        "checks": {}
    }

    # Database check (critical - required for readiness)
    try:
        from src.api.database.async_database import get_async_db_context
        async with get_async_db_context() as db:
            await db.execute(text("SELECT 1"))
            status["checks"]["database"] = "ready"
    except Exception as e:
        status["checks"]["database"] = f"not_ready: {str(e)}"
        status["status"] = "not_ready"

    # Redis check (optional - not required for readiness)
    try:
        from src.api.cache.redis_client import cache
        if cache.redis is not None:
            await cache.redis.ping()
            status["checks"]["redis"] = "ready"
        else:
            status["checks"]["redis"] = "not_configured"
    except ImportError:
        status["checks"]["redis"] = "not_configured"
    except Exception:
        status["checks"]["redis"] = "not_ready"
        # Don't mark overall as not_ready - cache is optional

    # Return appropriate status code
    status_code = 200 if status["status"] == "ready" else 503
    return JSONResponse(content=status, status_code=status_code)


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

    # Get configuration from settings
    host = settings.HOST
    port = settings.PORT
    debug = settings.DEBUG

    logger.info(f"Starting server on {host}:{port} (debug={debug})")

    uvicorn.run(
        app,
        host=host,
        port=port,
        reload=debug,
        access_log=True,
        log_level="info" if not debug else "debug"
    )
