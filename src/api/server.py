# Standard library imports
import asyncio
import sys
# 🩵 Fix for Playwright subprocess issue on Windows
if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
import os
from contextlib import asynccontextmanager
# Third-party imports
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from src.api.tool.routes import router as tool_router
# Local application imports
from src.api.database.async_database import async_engine
from src.api.middleware.request_tracker import RequestTrackerMiddleware
from src.api.middleware.error_handler import ErrorHandlerMiddleware, setup_exception_handlers
from src.api.middleware.security import SecurityHeadersMiddleware
from src.api.middleware.rate_limiter import RateLimiterMiddleware
from src.config.payment_config import payment_settings
from src.config.storage_config import storage_settings
from src.tasks.scheduled_tasks import start_scheduled_tasks, shutdown_scheduled_tasks
from src.api.cache.redis_client import cache
from src.api.config import settings
from src.utils.response_utils import success
from src.api.database.base import Base
from src.utils.logger import logger
from src.api.tool.routes import router as tool_router
# Structured logging
from src.api.lib.logging_config import configure_logging, RequestIDMiddleware

# Sentry error monitoring
from src.api.lib.sentry_config import init_sentry

from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware


load_dotenv()

# Configure structured logging at startup
configure_logging()

@asynccontextmanager
async def lifespan(app):
    """
    Application startup and shutdown lifecycle.
    Ensures database tables exist, Redis is connected,
    Sentry and tasks are initialized cleanly.
    """
    logger.info("🚀 Starting Rext API server...")
    logger.info(f"Environment: {settings.ENVIRONMENT}")

    # --- Initialize Sentry ---
    try:
        init_sentry(settings)
        logger.info("✅ Sentry initialized successfully")
    except Exception as e:
        logger.warning(
            "Failed to initialize Sentry",
            exc_info=True,
            extra={
                "error": str(e),
            }
        )

    # --- Connect Redis cache ---
    try:
        if not cache.redis:
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

    # --- Start background scheduled tasks ---
    try:
        start_scheduled_tasks()
        logger.info("✅ Scheduled tasks started")
    except Exception as e:
        logger.warning(
            "Failed to start scheduled tasks",
            exc_info=True,
            extra={
                "error": str(e),
            }
        )

    # --- Application is now ready ---
    logger.info("✅ Application startup complete. Ready to serve requests.")
    yield

    # --- Graceful shutdown ---
    logger.info("🛑 Shutting down application...")

    try:
        shutdown_scheduled_tasks()
        logger.info("✅ Scheduled tasks stopped")
    except Exception as e:
        logger.warning(
            "Failed to stop scheduled tasks",
            exc_info=True,
            extra={
                "error": str(e),
            }
        )

    try:
        await cache.disconnect()
        logger.info("✅ Redis cache disconnected")
    except Exception as e:
        logger.warning(f"⚠️ Failed to disconnect Redis: {e}")

    logger.info("👋 Application shutdown complete.")

app = FastAPI(
    title="Rext Content Automation API",
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
# NOTE: In Starlette/FastAPI, middleware added LAST is the OUTERMOST (processes
# requests first). CORS must be outermost so preflight OPTIONS requests get
# proper headers even if inner middleware returns early.

# Proxy headers middleware 
app.add_middleware(
    ProxyHeadersMiddleware,
    trusted_hosts=settings.TRUSTED_PROXY_IPS.split(",")
    if hasattr(settings, "TRUSTED_PROXY_IPS") and settings.TRUSTED_PROXY_IPS
    else ["127.0.0.1", "::1"]
)

# Request tracking middleware
app.add_middleware(
    RequestTrackerMiddleware,
    header_name="X-Request-ID",
    generate_if_missing=True,
    log_requests=True,
    include_processing_time=True
)

# Structured logging request ID middleware
app.add_middleware(RequestIDMiddleware)

# Sentry user context middleware
from src.api.middleware.sentry_middleware import SentryUserContextMiddleware
app.add_middleware(SentryUserContextMiddleware)

# Error handling middleware
app.add_middleware(
    ErrorHandlerMiddleware,
    include_debug_info=settings.DEBUG,
    log_full_traceback=True,
    filter_sensitive_data=True,
    max_error_details=10
)

# Security headers middleware
app.add_middleware(SecurityHeadersMiddleware)

# Rate limiting middleware
app.add_middleware(
    RateLimiterMiddleware,
    requests_per_minute=settings.RATE_LIMIT_PER_MINUTE,
    requests_per_hour=settings.RATE_LIMIT_PER_HOUR,
    requests_per_day=settings.RATE_LIMIT_PER_DAY,
    enable=settings.RATE_LIMITING_ENABLED
)

# CORS middleware (MUST be added last = outermost, so it handles preflight
# OPTIONS requests before any other middleware can intercept them)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=settings.cors_allowed_headers_list,
    expose_headers=["X-Request-ID", "Content-Type"],
    max_age=3600,
)

# Setup global exception handlers
setup_exception_handlers(app)

# ============================================================================
# ROUTE REGISTRATION
# ============================================================================

from src.api.registry.routes import register_routes
register_routes(app)

# ============================================================================
# STATIC FILE SERVING
# ============================================================================

# Mount media directory for serving uploaded files
# This allows the frontend to access media files via URLs like:
# http://localhost:2024/media/workspace-id/user-id/filename.jpg
media_dir = str(storage_settings.local_storage_path)
os.makedirs(media_dir, exist_ok=True)

app.mount("/media", StaticFiles(directory=media_dir), name="media")
logger.info("Mounted media directory for static file serving: %s", media_dir)

# ============================================================================
# ROOT ENDPOINTS
# ============================================================================

@app.get("/", tags=["Health"])
def read_root(request: Request):
    """Root endpoint with API information."""
    return success(
        data={
            "service": "Rext Content Automation API",
            "version": "1.0.0",
            "status": "operational",
            "docs_url": "/docs",
            "redoc_url": "/redoc",
            "openapi_url": "/openapi.json"
        },
        request=request,
        message="Welcome to Rext Content Automation API"
    )


@app.get("/health", tags=["Health"])
async def health_check(request: Request):
    """
    Comprehensive health check endpoint for monitoring.

    Returns overall system health with detailed dependency checks.
    Returns 200 if healthy, 503 if degraded.
    """
    from datetime import datetime, timezone
    from fastapi.responses import JSONResponse
    from sqlalchemy import text
    import shutil

    status = {
        "status": "healthy",
        "service": "rext-api",
        "version": "1.0.0",
        "environment": settings.ENVIRONMENT,
        "timestamp": datetime.now(timezone.utc).isoformat(),
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
    from datetime import datetime, timezone
    return {
        "status": "alive",
        "service": "rext-api",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@app.get("/health/ready", tags=["Health"])
async def readiness_check(request: Request):
    """
    Kubernetes readiness probe endpoint.

    Returns 200 if the application can accept traffic (all critical dependencies available).
    Returns 503 if dependencies are unavailable.
    Kubernetes will remove pod from load balancer if this returns non-200.
    """
    from datetime import datetime, timezone
    from fastapi.responses import JSONResponse
    from sqlalchemy import text

    status = {
        "status": "ready",
        "service": "rext-api",
        "timestamp": datetime.now(timezone.utc).isoformat(),
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
