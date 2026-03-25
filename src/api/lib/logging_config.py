"""Structured logging configuration using structlog."""
import logging
import structlog
import uuid
import time
from typing import Optional, Dict, Any
from contextlib import contextmanager
from dataclasses import dataclass, asdict
from src.api.config import get_settings


def configure_logging():
    """Configure structured logging for the application."""
    settings = get_settings()
    logging.basicConfig(
        format="%(message)s",
        level=getattr(logging, settings.LOG_LEVEL),
    )

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer() if settings.is_production
                else structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.BoundLogger:
    """Get a logger instance."""
    return structlog.get_logger(name)



class RequestIDMiddleware:
    """Middleware to add request ID tracking to all requests.
    Using pure ASGI interface to avoid BaseHTTPMiddleware issues with streaming responses.
    """
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Try to get request ID from headers
        request_id = None
        for header, value in scope.get("headers", []):
            if header.lower() == b"x-request-id":
                request_id = value.decode()
                break
        
        if not request_id:
            request_id = str(uuid.uuid4())

        structlog.contextvars.bind_contextvars(request_id=request_id)

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                
                # Check if header already exists
                has_header = False
                for k, v in headers:
                    if k.lower() == b"x-request-id":
                        has_header = True
                        break
                
                if not has_header:
                    headers.append((b"X-Request-ID", request_id.encode()))
                
                message["headers"] = headers
            
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            structlog.contextvars.clear_contextvars()


# ============================================================================
# Payment Logging Utilities (Phase 4, Task 4.2.2)
# ============================================================================


@dataclass
class PaymentLogContext:
    """Structured context for payment operation logs."""
    operation: str  # checkout, webhook, update, cancel, refund
    provider: str = "lemonsqueezy"
    user_id: Optional[str] = None
    subscription_id: Optional[str] = None
    customer_id: Optional[str] = None
    plan_id: Optional[str] = None
    variant_id: Optional[str] = None
    status: Optional[str] = None
    amount: Optional[int] = None
    currency: Optional[str] = None
    event_type: Optional[str] = None
    correlation_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict, excluding None values."""
        return {k: v for k, v in asdict(self).items() if v is not None}


def generate_payment_correlation_id() -> str:
    """
    Generate a unique correlation ID for payment operations.

    This ID can be used to trace a payment operation across multiple
    services, logs, and monitoring systems.

    Returns:
        Unique correlation ID (UUID format)
    """
    return f"pay_{uuid.uuid4().hex[:16]}"


def bind_payment_context(
    operation: str,
    user_id: Optional[str] = None,
    subscription_id: Optional[str] = None,
    customer_id: Optional[str] = None,
    **kwargs
) -> None:
    """
    Bind payment context to the current structlog context.

    This adds structured payment-specific fields to all subsequent log
    messages in the current execution context.

    Args:
        operation: Payment operation type (checkout, webhook, update, etc.)
        user_id: User ID involved in the operation
        subscription_id: Subscription ID (if applicable)
        customer_id: Payment provider customer ID
        **kwargs: Additional context fields

    Example:
        >>> bind_payment_context(
        ...     operation="checkout",
        ...     user_id="user_123",
        ...     plan_id="plan_456"
        ... )
    """
    context = PaymentLogContext(
        operation=operation,
        user_id=user_id,
        subscription_id=subscription_id,
        customer_id=customer_id,
        **kwargs
    )
    structlog.contextvars.bind_contextvars(**context.to_dict())


def log_payment_operation(
    logger: structlog.BoundLogger,
    level: str,
    message: str,
    operation: str,
    **context
) -> None:
    """
    Log a payment operation with structured context.

    This is a convenience function for logging payment operations with
    consistent structure and fields.

    Args:
        logger: Structlog logger instance
        level: Log level (info, warning, error, debug)
        message: Log message
        operation: Payment operation type
        **context: Additional context fields

    Example:
        >>> log_payment_operation(
        ...     logger,
        ...     "info",
        ...     "Checkout session created",
        ...     operation="checkout",
        ...     session_id="ses_123",
        ...     amount=2999
        ... )
    """
    log_context = PaymentLogContext(operation=operation, **context)
    log_method = getattr(logger, level.lower())
    log_method(message, **log_context.to_dict())


@contextmanager
def log_payment_timing(
    logger: structlog.BoundLogger,
    operation: str,
    message: str,
    level: str = "info",
    **context
):
    """
    Context manager for logging payment operation timing.

    Automatically logs the duration of a payment operation and handles
    exceptions by logging them as errors.

    Args:
        logger: Structlog logger instance
        operation: Payment operation type
        message: Log message describing the operation
        level: Log level for success (default: info)
        **context: Additional context fields

    Yields:
        Dict that can be updated with additional context during execution

    Example:
        >>> with log_payment_timing(logger, "checkout", "Creating checkout session") as ctx:
        ...     session = await create_session()
        ...     ctx["session_id"] = session.id
    """
    start_time = time.time()
    execution_context = {}

    try:
        logger.debug(
            f"{message} - started",
            operation=operation,
            **context
        )
        yield execution_context

        duration_ms = int((time.time() - start_time) * 1000)
        log_method = getattr(logger, level.lower())
        log_method(
            f"{message} - completed",
            operation=operation,
            duration_ms=duration_ms,
            **{**context, **execution_context}
        )

    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.error(
            f"{message} - failed",
            operation=operation,
            duration_ms=duration_ms,
            error=str(e),
            error_type=type(e).__name__,
            **{**context, **execution_context}
        )
        raise


def clear_payment_context() -> None:
    """
    Clear payment-specific context from structlog.

    Call this after a payment operation completes to prevent context
    bleeding into subsequent operations.
    """
    structlog.contextvars.clear_contextvars()
