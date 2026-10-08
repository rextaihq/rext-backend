"""
Sentry Error Monitoring Configuration

This module initializes and configures Sentry SDK for error tracking,
performance monitoring, and alerting in the REXT backend application.

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
from typing import Any, Dict, Optional

import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.logging import LoggingIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration

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
            traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE
            if settings.SENTRY_ENABLE_TRACING
            else 0.0,
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
                    failed_request_status_codes=[
                        500,
                        501,
                        502,
                        503,
                        504,
                        505,
                    ],  # Track 5xx as errors
                ),
                # Starlette integration (underlying FastAPI framework)
                StarletteIntegration(
                    transaction_style="url",
                    failed_request_status_codes=[500, 501, 502, 503, 504, 505],
                ),
                # SQLAlchemy integration (database query tracking)
                SqlalchemyIntegration(),
                # Logging integration (capture log messages as breadcrumbs)
                LoggingIntegration(
                    level=logging.INFO,  # Capture info and above as breadcrumbs
                    event_level=logging.ERROR,  # Send error logs as events
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
        sentry_sdk.set_tag("app", "rext-backend")
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

    # An error its code reports in its own way (suppress_error_log, which keeps it out of the Error
    # Logs too): a free tool's 503 while the AI provider is down is alerted once an hour, not per request.
    exc_info = hint.get("exc_info") if isinstance(hint, dict) else None
    if exc_info and getattr(exc_info[1], "suppress_error_log", False):
        return None

    # Add custom fingerprinting for better grouping
    if "exception" in event:
        exc_values = event["exception"].get("values", [])
        if exc_values:
            exc_type = exc_values[0].get("type", "")
            exc_value = exc_values[0].get("value", "")

            # Payment-specific error grouping (Phase 4, Task 4.2.1)
            tags = event.get("tags", {})
            if tags.get("payment_operation"):
                # Group payment errors by: provider + operation + error type + status code
                operation = tags.get("payment_operation", "unknown")
                provider = tags.get("payment_provider", "unknown")

                # Extract status code from LemonSqueezy API errors
                status_code = "unknown"
                if "LemonSqueezyAPIError" in exc_type:
                    # Parse status code from error message "LemonSqueezy API Error (404): ..."
                    import re

                    match = re.search(r"\((\d+)\)", exc_value)
                    if match:
                        status_code = match.group(1)

                event["fingerprint"] = [provider, operation, exc_type, status_code]
            else:
                # Default grouping: exception type + first line of message
                first_line = exc_value.split("\n")[0] if exc_value else ""
                event["fingerprint"] = [exc_type, first_line]

    return event


def before_breadcrumb_filter(
    crumb: Dict[str, Any], hint: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
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

    # Payment endpoints at maximum rate (Phase 4, Task 4.2.1)
    # These are critical revenue-generating operations
    if "/subscriptions/checkout" in path or "/subscriptions/webhook" in path:
        return 1.0  # 100% - critical payment operations

    # Other payment endpoints at high rate
    if any(segment in path for segment in ["/subscriptions/", "/plans/", "/trials/"]):
        return 0.8  # 80%

    # Sample admin endpoints at higher rate
    if "/admin/" in path:
        return 0.5  # 50%

    # Default sampling rate from settings
    from src.api.config import get_settings

    settings = get_settings()
    return settings.SENTRY_TRACES_SAMPLE_RATE


def capture_exception_with_context(
    exception: Exception,
    context: Optional[Dict[str, Any]] = None,
    level: str = "error",
    tags: Optional[Dict[str, str]] = None,
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
    data: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Add a breadcrumb for debugging context.

    Args:
        message: Breadcrumb message
        category: Category for filtering (e.g., "auth", "database", "api")
        level: Severity level
        data: Additional structured data
    """
    sentry_sdk.add_breadcrumb(message=message, category=category, level=level, data=data or {})


def set_user_context(
    user_id: str, email: Optional[str] = None, username: Optional[str] = None
) -> None:
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


# ============================================================================
# Payment-Specific Sentry Helpers (Phase 4, Task 4.2.1)
# ============================================================================


def capture_payment_exception(
    exception: Exception,
    operation: str,
    context: Optional[Dict[str, Any]] = None,
    level: str = "error",
    user_id: Optional[str] = None,
    subscription_id: Optional[str] = None,
    customer_id: Optional[str] = None,
    plan_id: Optional[str] = None,
    amount: Optional[float] = None,
) -> Optional[str]:
    """
    Capture a payment-related exception with rich context.

    This function adds payment-specific tags and context to make it easy
    to filter and analyze payment errors in Sentry.

    Args:
        exception: Exception to capture
        operation: Payment operation (e.g., "checkout", "cancel", "upgrade", "webhook")
        context: Additional context data
        level: Severity level (debug/info/warning/error/fatal)
        user_id: User ID associated with the payment operation
        subscription_id: Subscription ID if applicable
        customer_id: LemonSqueezy customer ID
        plan_id: Subscription plan ID
        amount: Payment amount if applicable

    Returns:
        Event ID if sent to Sentry, None otherwise

    Example:
        >>> try:
        ...     await provider.create_checkout(...)
        ... except LemonSqueezyAPIError as e:
        ...     capture_payment_exception(
        ...         e,
        ...         operation="checkout",
        ...         user_id="user_123",
        ...         plan_id="plan_456",
        ...         amount=29.99
        ...     )
    """
    with sentry_sdk.push_scope() as scope:
        # Add payment-specific tags for filtering
        scope.set_tag("payment_operation", operation)
        scope.set_tag("payment_provider", "lemonsqueezy")

        if subscription_id:
            scope.set_tag("subscription_id", subscription_id)

        if customer_id:
            scope.set_tag("customer_id", customer_id)

        if plan_id:
            scope.set_tag("plan_id", plan_id)

        # Add payment context
        payment_context = {
            "operation": operation,
            "provider": "lemonsqueezy",
        }

        if user_id:
            payment_context["user_id"] = user_id

        if subscription_id:
            payment_context["subscription_id"] = subscription_id

        if customer_id:
            payment_context["customer_id"] = customer_id

        if plan_id:
            payment_context["plan_id"] = plan_id

        if amount is not None:
            payment_context["amount"] = amount

        # Merge with additional context
        if context:
            payment_context.update(context)

        scope.set_context("payment", payment_context)

        # Set level
        scope.level = level

        # Capture exception
        event_id = sentry_sdk.capture_exception(exception)

        if event_id:
            logger.info(
                f"Captured payment exception to Sentry: {event_id} "
                f"(operation={operation}, provider=lemonsqueezy)"
            )

        return event_id


def set_payment_context(
    operation: str,
    user_id: Optional[str] = None,
    subscription_id: Optional[str] = None,
    customer_id: Optional[str] = None,
    plan_id: Optional[str] = None,
    amount: Optional[float] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Set payment context for all subsequent events in this scope.

    Use this at the beginning of payment operations to enrich all
    Sentry events (including breadcrumbs) with payment context.

    Args:
        operation: Payment operation type
        user_id: User ID
        subscription_id: Subscription ID
        customer_id: LemonSqueezy customer ID
        plan_id: Plan ID
        amount: Payment amount
        metadata: Additional metadata

    Example:
        >>> set_payment_context(
        ...     operation="checkout",
        ...     user_id="user_123",
        ...     plan_id="plan_456",
        ...     amount=29.99
        ... )
    """
    payment_context = {
        "operation": operation,
        "provider": "lemonsqueezy",
    }

    if user_id:
        payment_context["user_id"] = user_id

    if subscription_id:
        payment_context["subscription_id"] = subscription_id

    if customer_id:
        payment_context["customer_id"] = customer_id

    if plan_id:
        payment_context["plan_id"] = plan_id

    if amount is not None:
        payment_context["amount"] = amount

    if metadata:
        payment_context["metadata"] = metadata

    sentry_sdk.set_context("payment", payment_context)

    # Also set as tags for easy filtering
    sentry_sdk.set_tag("payment_operation", operation)
    sentry_sdk.set_tag("payment_provider", "lemonsqueezy")


def add_payment_breadcrumb(
    message: str,
    operation: str,
    level: str = "info",
    data: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Add a payment-specific breadcrumb for debugging.

    Use this to track payment operation steps and make it easier
    to debug payment issues.

    Args:
        message: Breadcrumb message
        operation: Payment operation type
        level: Severity level
        data: Additional structured data

    Example:
        >>> add_payment_breadcrumb(
        ...     "Creating checkout session",
        ...     operation="checkout",
        ...     data={"plan_id": "plan_456", "amount": 29.99}
        ... )
    """
    breadcrumb_data = {
        "operation": operation,
        "provider": "lemonsqueezy",
    }

    if data:
        breadcrumb_data.update(data)

    sentry_sdk.add_breadcrumb(
        message=message, category="payment", level=level, data=breadcrumb_data
    )


# ============================================================================
# Payment Alert Functions (Phase 4, Task 4.2.3)
# ============================================================================


def trigger_payment_alert(
    alert_type: str,
    message: str,
    severity: str = "high",
    context: Optional[Dict[str, Any]] = None,
    user_id: Optional[str] = None,
    subscription_id: Optional[str] = None,
    operation: Optional[str] = None,
) -> None:
    """
    Trigger a high-priority Sentry alert for critical payment failures.

    This function captures events with specific tags that match alert rules
    configured in the Sentry dashboard. Use this for failures that require
    immediate attention.

    Args:
        alert_type: Type of alert (webhook_failure, api_error, subscription_failure, etc.)
        message: Alert message describing the failure
        severity: Alert severity (critical, high, medium, low)
        context: Additional context for debugging
        user_id: User ID affected by the failure
        subscription_id: Subscription ID affected by the failure
        operation: Payment operation that failed

    Example:
        >>> trigger_payment_alert(
        ...     alert_type="webhook_signature_failure",
        ...     message="Webhook signature verification failed",
        ...     severity="high",
        ...     context={"attempts": 3, "endpoint": "/webhooks/lemonsqueezy"}
        ... )
    """
    # Prepare alert context
    alert_context = {
        "alert_type": alert_type,
        "severity": severity,
    }

    if context:
        alert_context.update(context)

    # Set alert tags for filtering in Sentry
    with sentry_sdk.push_scope() as scope:
        # Core alert tags
        scope.set_tag("alert", "true")
        scope.set_tag("alert_type", alert_type)
        scope.set_tag("alert_severity", severity)

        # Payment-specific tags
        if operation:
            scope.set_tag("payment_operation", operation)
        if user_id:
            scope.set_tag("user_id", user_id)
        if subscription_id:
            scope.set_tag("subscription_id", subscription_id)

        # Always tag with provider
        scope.set_tag("payment_provider", "lemonsqueezy")

        # Set alert context
        scope.set_context("alert", alert_context)

        # Set appropriate level based on severity
        level_map = {
            "critical": "error",
            "high": "error",
            "medium": "warning",
            "low": "info",
        }
        sentry_level = level_map.get(severity.lower(), "error")

        # Capture the alert event
        sentry_sdk.capture_message(message, level=sentry_level)


def alert_webhook_signature_failure(
    payload_length: int,
    endpoint: str = "/webhooks/lemonsqueezy",
    additional_context: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Alert on webhook signature verification failure.

    This indicates a potential security issue - either an attacker is
    sending fake webhooks, or the webhook secret is misconfigured.

    Args:
        payload_length: Length of the payload that failed verification
        endpoint: Webhook endpoint that received the request
        additional_context: Additional debugging context

    Alert Rule:
        - Trigger: 3+ failures in 5 minutes
        - Severity: HIGH
        - Notification: Email + Slack
    """
    context = {
        "payload_length": payload_length,
        "endpoint": endpoint,
        "category": "security",
        "revenue_impact": "potential",
    }

    if additional_context:
        context.update(additional_context)

    trigger_payment_alert(
        alert_type="webhook_signature_failure",
        message=f"Webhook signature verification failed on {endpoint}",
        severity="high",
        context=context,
        operation="webhook_verification",
    )


def alert_api_error(
    method: str,
    endpoint: str,
    status_code: int,
    error_message: str,
    operation: str,
    user_id: Optional[str] = None,
    subscription_id: Optional[str] = None,
) -> None:
    """
    Alert on LemonSqueezy API errors.

    API errors can indicate service outages, rate limiting, or
    configuration issues. High error rates directly impact revenue.

    Args:
        method: HTTP method (GET, POST, PATCH, DELETE)
        endpoint: API endpoint that failed
        status_code: HTTP status code returned
        error_message: Error message from API
        operation: Payment operation (checkout, cancel_subscription, etc.)
        user_id: User ID affected
        subscription_id: Subscription ID affected

    Alert Rule:
        - Trigger: 5+ errors in 10 minutes
        - Severity: CRITICAL
        - Notification: Email + PagerDuty
    """
    context = {
        "method": method,
        "endpoint": endpoint,
        "status_code": status_code,
        "error_message": error_message,
        "category": "api_error",
        "revenue_impact": "direct",
    }

    trigger_payment_alert(
        alert_type="api_error",
        message=f"LemonSqueezy API error: {method} {endpoint} returned {status_code}",
        severity="critical" if status_code >= 500 else "high",
        context=context,
        operation=operation,
        user_id=user_id,
        subscription_id=subscription_id,
    )


def alert_subscription_creation_failure(
    user_id: str,
    variant_id: str,
    error_message: str,
    event_id: Optional[str] = None,
) -> None:
    """
    Alert on failed subscription creation from webhook.

    Failed subscription creations mean a user paid but didn't get access.
    This is a critical revenue and customer satisfaction issue.

    Args:
        user_id: User ID for the failed subscription
        variant_id: LemonSqueezy variant ID
        error_message: Error message describing the failure
        event_id: Webhook event ID

    Alert Rule:
        - Trigger: 2+ failures in 15 minutes
        - Severity: CRITICAL
        - Notification: Email + PagerDuty
    """
    context = {
        "variant_id": variant_id,
        "error_message": error_message,
        "event_id": event_id,
        "category": "subscription_failure",
        "revenue_impact": "direct",
        "customer_impact": "high",
    }

    trigger_payment_alert(
        alert_type="subscription_creation_failure",
        message=f"Failed to create subscription for user {user_id}",
        severity="critical",
        context=context,
        operation="webhook_subscription_created",
        user_id=user_id,
    )


def alert_checkout_failure(
    user_id: str,
    variant_id: str,
    error_message: str,
    correlation_id: Optional[str] = None,
) -> None:
    """
    Alert on checkout session creation failures.

    Checkout failures prevent users from starting the payment flow,
    directly impacting revenue.

    Args:
        user_id: User ID attempting checkout
        variant_id: LemonSqueezy variant ID
        error_message: Error message describing the failure
        correlation_id: Correlation ID for tracing

    Alert Rule:
        - Trigger: 3+ failures in 10 minutes
        - Severity: HIGH
        - Notification: Email + Slack
    """
    context = {
        "variant_id": variant_id,
        "error_message": error_message,
        "correlation_id": correlation_id,
        "category": "checkout_failure",
        "revenue_impact": "direct",
    }

    trigger_payment_alert(
        alert_type="checkout_failure",
        message=f"Checkout creation failed for user {user_id}",
        severity="high",
        context=context,
        operation="checkout",
        user_id=user_id,
    )


def alert_cancellation_error(
    subscription_id: str,
    user_id: str,
    error_message: str,
) -> None:
    """
    Alert on subscription cancellation errors.

    While less critical than creation failures, cancellation errors
    can frustrate users and create support burden.

    Args:
        subscription_id: Subscription ID that failed to cancel
        user_id: User ID requesting cancellation
        error_message: Error message describing the failure

    Alert Rule:
        - Trigger: 5+ errors in 30 minutes
        - Severity: MEDIUM
        - Notification: Email
    """
    context = {
        "error_message": error_message,
        "category": "cancellation_error",
        "customer_impact": "medium",
    }

    trigger_payment_alert(
        alert_type="cancellation_error",
        message=f"Failed to cancel subscription {subscription_id}",
        severity="medium",
        context=context,
        operation="cancel_subscription",
        user_id=user_id,
        subscription_id=subscription_id,
    )


def alert_slow_webhook_processing(
    event_type: str,
    duration_ms: int,
    event_id: Optional[str] = None,
    subscription_id: Optional[str] = None,
) -> None:
    """
    Alert on slow webhook processing (Phase 4, Task 4.2.4).

    Slow webhook processing can indicate performance issues that may
    lead to timeouts or degraded user experience.

    Args:
        event_type: Type of webhook event (subscription_created, etc.)
        duration_ms: Processing time in milliseconds
        event_id: Webhook event ID
        subscription_id: Subscription ID (if applicable)

    Alert Rule:
        - Trigger: Processing time > 5000ms (5 seconds)
        - Severity: MEDIUM
        - Notification: Email + Slack
    """
    context = {
        "event_type": event_type,
        "duration_ms": duration_ms,
        "event_id": event_id,
        "threshold_ms": 5000,
        "category": "performance",
        "performance_impact": "high",
    }

    trigger_payment_alert(
        alert_type="slow_webhook_processing",
        message=f"Webhook processing exceeded 5s threshold: {event_type} took {duration_ms}ms",
        severity="medium",
        context=context,
        operation=f"webhook_{event_type}",
        subscription_id=subscription_id,
    )
