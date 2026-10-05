import logging
from enum import Enum

logger = logging.getLogger(__name__)


class ExternalServiceCategory(Enum):
    RATE_LIMITED = "RATE_LIMITED"
    AUTH_FAILURE = "AUTH_FAILURE"
    TIMEOUT = "TIMEOUT"
    UNAVAILABLE = "UNAVAILABLE"
    INVALID_RESPONSE = "INVALID_RESPONSE"
    GENERIC = "GENERIC"


SAFE_MESSAGES = {
    ExternalServiceCategory.RATE_LIMITED: "This request couldn't be completed right now. Please try again later.",
    ExternalServiceCategory.AUTH_FAILURE: "The service is temporarily unavailable. Please try again later.",
    ExternalServiceCategory.TIMEOUT: "We couldn't complete this request right now. Please try again in a moment.",
    ExternalServiceCategory.UNAVAILABLE: "The service is temporarily unavailable. Please try again later.",
    ExternalServiceCategory.INVALID_RESPONSE: "We received an unexpected response from the service. Please try again.",
    ExternalServiceCategory.GENERIC: "We couldn't complete this request right now. Please try again in a moment.",
}


def classify_provider_exception(exc: Exception, provider_name: str = "") -> ExternalServiceCategory:
    # Check for specific class names to avoid direct imports causing ImportErrors
    exc_type_name = type(exc).__name__

    # OpenAI exceptions
    if exc_type_name == "RateLimitError":
        return ExternalServiceCategory.RATE_LIMITED
    if exc_type_name == "AuthenticationError":
        return ExternalServiceCategory.AUTH_FAILURE
    if exc_type_name in ("APITimeoutError", "TimeoutError"):
        return ExternalServiceCategory.TIMEOUT
    if exc_type_name == "APIConnectionError":
        return ExternalServiceCategory.UNAVAILABLE

    # httpx / requests
    if exc_type_name in ("TimeoutException", "ConnectTimeout", "ReadTimeout"):
        return ExternalServiceCategory.TIMEOUT
    if exc_type_name in ("ConnectError", "ConnectionError"):
        return ExternalServiceCategory.UNAVAILABLE

    # Python built-in timeouts
    if exc_type_name == "TimeoutError":
        return ExternalServiceCategory.TIMEOUT

    # HTTP Status Errors (like httpx.HTTPStatusError)
    if hasattr(exc, "response") and exc.response is not None:
        status_code = getattr(exc.response, "status_code", None)
        if status_code == 429:
            return ExternalServiceCategory.RATE_LIMITED
        if status_code in (401, 403):
            return ExternalServiceCategory.AUTH_FAILURE
        if status_code and 500 <= status_code < 600:
            return ExternalServiceCategory.UNAVAILABLE

    return ExternalServiceCategory.GENERIC


def safe_user_message(category: ExternalServiceCategory, context: str = "") -> str:
    return SAFE_MESSAGES.get(category, SAFE_MESSAGES[ExternalServiceCategory.GENERIC])


def log_provider_error(
    logger_instance: logging.Logger,
    exc: Exception,
    provider_name: str,
    operation: str,
    extra: dict = None,
) -> None:
    category = classify_provider_exception(exc, provider_name)
    logger_instance.error(
        f"External service error: provider={provider_name} operation={operation} category={category.value}",
        exc_info=True,
        extra=extra or {},
    )
