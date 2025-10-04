"""Logger utilities with automatic module naming and sensitive data sanitization."""
from src.api.lib.logging_config import get_logger
from typing import Any
import inspect


def auto_logger():
    """Get logger with automatic module name."""
    frame = inspect.currentframe()
    if frame and frame.f_back:
        module = inspect.getmodule(frame.f_back)
        if module:
            return get_logger(module.__name__)
    return get_logger("app")


SENSITIVE_KEYS = {"password", "token", "secret", "api_key", "authorization", "refresh_token", "access_token"}


def sanitize_dict(data: dict[str, Any]) -> dict[str, Any]:
    """Remove sensitive data from dict for logging."""
    sanitized = {}
    for key, value in data.items():
        if any(sensitive in key.lower() for sensitive in SENSITIVE_KEYS):
            sanitized[key] = "***REDACTED***"
        elif isinstance(value, dict):
            sanitized[key] = sanitize_dict(value)
        elif isinstance(value, list):
            sanitized[key] = [sanitize_dict(item) if isinstance(item, dict) else item for item in value]
        else:
            sanitized[key] = value
    return sanitized
