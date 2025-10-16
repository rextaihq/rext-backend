"""
Sentry Error Monitoring Configuration

This module initializes and configures Sentry SDK for error tracking,
performance monitoring, and alerting in the WREXT backend application.

Features:
- Automatic error capture and reporting
- Performance transaction tracking
- User context enrichment
- Custom tags for better filtering
- Integration with FastAPI and SQLAlchemy
- Release tracking for deployments
- Breadcrumb logging for debugging
"""

import logging
import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
from sentry_sdk.integrations.logging import LoggingIntegration
from typing import Optional, Dict, Any

from src.api.config import Settings

logger = logging.getLogger(__name__)


def init_sentry(settings: Settings) -> None:
    """
    Initialize Sentry SDK with application-specific configuration.

    Args:
        settings: Application settings containing Sentry configuration

    Returns:
        None (Sentry SDK is initialized globally)

    Raises:
        Warning if Sentry initialization fails (non-blocking)
    """
    if not settings.sentry_enabled:
        logger.info("Sentry monitoring disabled (SENTRY_DSN not configured)")
        return

    try:
        sentry_sdk.init(
            # Core Configuration
            dsn=settings.SENTRY_DSN,
            environment=settings.sentry_environment,
            release=settings.SENTRY_RELEASE,

            # Performance Monitoring
            traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE if settings.SENTRY_ENABLE_TRACING else 0.0,
            profiles_sample_rate=settings.SENTRY_PROFILES_SAMPLE_RATE,

            # Privacy & Security
            send_default_pii=settings.SENTRY_SEND_DEFAULT_PII,
            attach_stacktrace=settings.SENTRY_ATTACH_STACKTRACE,
            max_breadcrumbs=settings.SENTRY_MAX_BREADCRUMBS,

            # Debug Mode
            debug=settings.SENTRY_DEBUG,

            # Integrations - Explicitly defined to prevent auto-enabling conflicts
            #
            # CRITICAL: OpenAI Integration Conflict with LangChain/LangGraph
            # =============================================================
            # The Sentry OpenAI integration (auto-enabled when `openai` package detected)
            # conflicts with LangChain's `with_structured_output()` method, causing:
            #   TypeError: object of type 'Omit' has no len()
            #   at /sentry_sdk/integrations/openai.py:212 in _set_input_data()
            #
            # Root Cause:
            # - Sentry tries to inspect `tools` parameter with `len(tools)`
            # - LangChain passes an `Omit` type object (not a list) when using structured output
            # - This breaks content generation with LangGraph workflows
            #
            # Solution:
            # - Explicitly define integrations list (prevents auto-discovery)
            # - Do NOT include OpenAIIntegration
            # - Set default_integrations=False and auto_enabling_integrations=False
            #
            # Trade-off:
            # - We lose OpenAI request tracing in Sentry
            # - We keep all other monitoring (FastAPI, SQLAlchemy, logging)
            # - Content generation works correctly
            #
            # References:
            # - Sentry OpenAI Integration: https://docs.sentry.io/platforms/python/integrations/openai/
            # - LangGraph Integration Note: "For correct token accounting, disable the
            #   integration for the model provider you are using (e.g. OpenAI)"
            # - Similar issues: BaseModel.model_dump() TypeError with structured output
            integrations=[
                # FastAPI integration (automatic request tracking)
                FastApiIntegration(
                    transaction_style="url",  # Use URL patterns for transaction names
                    failed_request_status_codes=[500, 501, 502, 503, 504, 505]  # Track 5xx as errors
                ),

                # Starlette integration (underlying FastAPI framework)
                StarletteIntegration(
                    transaction_style="url",
                    failed_request_status_codes=[500, 501, 502, 503, 504, 505]
                ),

                # SQLAlchemy integration (database query tracking)
                SqlalchemyIntegration(),

                # Logging integration (capture log messages as breadcrumbs)
                LoggingIntegration(
                    level=logging.INFO,        # Capture info and above as breadcrumbs
                    event_level=logging.ERROR  # Send error logs as events
                ),
                # OpenAIIntegration - intentionally EXCLUDED (see comment above)
                # LangGraphIntegration - not added to avoid double-tracking with LangSmith
            ],

            # Disable auto-discovery to prevent OpenAI integration from being auto-enabled
            default_integrations=False,
            auto_enabling_integrations=False,

            # Error Filtering
            before_send=before_send_filter,
            before_breadcrumb=before_breadcrumb_filter,

            # Additional Options
            traces_sampler=traces_sampler,
        )

        # Set global tags for all events
        sentry_sdk.set_tag("app", "wrext-backend")
        sentry_sdk.set_tag("environment", settings.sentry_environment)

        logger.info(
            f"✅ Sentry initialized successfully "
            f"(environment: {settings.sentry_environment}, "
            f"traces_sample_rate: {settings.SENTRY_TRACES_SAMPLE_RATE})"
        )

    except Exception as e:
        # Non-blocking: log error but don't crash the application
        logger.error(f"Failed to initialize Sentry: {e}", exc_info=True)


def before_send_filter(event: Dict[str, Any], hint: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Filter and modify events before sending to Sentry.

    This function allows us to:
    - Filter out low-priority errors
    - Sanitize sensitive data
    - Add custom context
    - Drop events based on conditions

    Args:
        event: Sentry event dictionary
        hint: Additional context about the event

    Returns:
        Modified event dictionary, or None to drop the event
    """
    # Drop health check 404s (not real errors)
    if event.get("request", {}).get("url", "").endswith("/health"):
        return None

    # Drop rate limit errors (expected behavior)
    if "RateLimitExceededException" in str(event.get("exception", {})):
        return None

    # Add custom fingerprinting for better grouping
    if "exception" in event:
        exc_values = event["exception"].get("values", [])
        if exc_values:
            exc_type = exc_values[0].get("type", "")
            exc_value = exc_values[0].get("value", "")

            # Group by exception type + first line of message
            first_line = exc_value.split("\n")[0] if exc_value else ""
            event["fingerprint"] = [exc_type, first_line]

    return event


def before_breadcrumb_filter(crumb: Dict[str, Any], hint: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Filter and modify breadcrumbs before adding to event.

    Args:
        crumb: Breadcrumb dictionary
        hint: Additional context about the breadcrumb

    Returns:
        Modified breadcrumb dictionary, or None to drop the breadcrumb
    """
    # Drop noisy breadcrumbs
    if crumb.get("category") == "query" and "SELECT 1" in str(crumb.get("message", "")):
        return None  # Drop health check queries

    # Sanitize SQL queries (remove actual values)
    if crumb.get("category") == "query":
        message = crumb.get("message", "")
        if "password" in message.lower() or "secret" in message.lower():
            crumb["message"] = "[REDACTED SQL QUERY]"

    return crumb


def traces_sampler(sampling_context: Dict[str, Any]) -> float:
    """
    Dynamic trace sampling based on request characteristics.

    Args:
        sampling_context: Context about the current transaction

    Returns:
        Sample rate (0.0 to 1.0) for this transaction
    """
    # Always sample errors
    if sampling_context.get("parent_sampled") is True:
        return 1.0

    # Extract ASGI scope (FastAPI request context)
    asgi_scope = sampling_context.get("asgi_scope", {})
    path = asgi_scope.get("path", "")

    # Sample health checks at lower rate
    if path in ["/health", "/readiness", "/liveness"]:
        return 0.01  # 1%

    # Sample admin endpoints at higher rate
    if "/admin/" in path:
        return 0.5  # 50%

    # Sample AI endpoints at higher rate (expensive operations)
    if any(segment in path for segment in ["/content/generate", "/topics/generate", "/knowledge/process"]):
        return 0.8  # 80%

    # Default sampling rate from settings
    from src.api.config import get_settings
    settings = get_settings()
    return settings.SENTRY_TRACES_SAMPLE_RATE


def capture_exception_with_context(
    exception: Exception,
    context: Optional[Dict[str, Any]] = None,
    level: str = "error",
    tags: Optional[Dict[str, str]] = None
) -> Optional[str]:
    """
    Capture an exception with additional context.

    Args:
        exception: Exception to capture
        context: Additional context data
        level: Severity level (debug/info/warning/error/fatal)
        tags: Custom tags for filtering

    Returns:
        Event ID if sent to Sentry, None otherwise
    """
    with sentry_sdk.push_scope() as scope:
        # Add custom context
        if context:
            scope.set_context("custom", context)

        # Add custom tags
        if tags:
            for key, value in tags.items():
                scope.set_tag(key, value)

        # Set level
        scope.level = level

        # Capture exception
        event_id = sentry_sdk.capture_exception(exception)

        if event_id:
            logger.info(f"Captured exception to Sentry: {event_id}")

        return event_id


def add_breadcrumb(
    message: str,
    category: str = "custom",
    level: str = "info",
    data: Optional[Dict[str, Any]] = None
) -> None:
    """
    Add a breadcrumb for debugging context.

    Args:
        message: Breadcrumb message
        category: Category for filtering (e.g., "auth", "database", "api")
        level: Severity level
        data: Additional structured data
    """
    sentry_sdk.add_breadcrumb(
        message=message,
        category=category,
        level=level,
        data=data or {}
    )


def set_user_context(user_id: str, email: Optional[str] = None, username: Optional[str] = None) -> None:
    """
    Set user context for all subsequent events in this scope.

    Args:
        user_id: User ID
        email: User email (optional, respects SENTRY_SEND_DEFAULT_PII)
        username: Username (optional)
    """
    from src.api.config import get_settings
    settings = get_settings()

    user_data = {"id": user_id}

    # Only add PII if explicitly enabled
    if settings.SENTRY_SEND_DEFAULT_PII:
        if email:
            user_data["email"] = email
        if username:
            user_data["username"] = username

    sentry_sdk.set_user(user_data)


def clear_user_context() -> None:
    """Clear user context (e.g., after request completes)."""
    sentry_sdk.set_user(None)
