from __future__ import annotations

from typing import Literal

LogLevel = Literal["debug", "info", "warning", "error", "critical"]

EVENT_LEVELS: dict[str, LogLevel] = {
    "request_start": "info",
    "request_success": "info",
    "request_error": "error",
    "permission_denied": "warning",
    "permission_granted": "debug",
    "rate_limit_exceeded": "warning",
    "transaction_committed": "debug",
    "transaction_rolled_back": "warning",
}

SEVERITY_LEVELS: dict[str, LogLevel] = {
    "critical": "error",
    "high": "error",
    "medium": "warning",
    "low": "info",
}


def get_event_level(event_type: str, default: LogLevel = "info") -> LogLevel:
    return EVENT_LEVELS.get(event_type, default)


def get_severity_level(severity: str, default: LogLevel = "warning") -> LogLevel:
    return SEVERITY_LEVELS.get(severity.lower(), default)


def log_with_level(logger, level: LogLevel, message: str, **kwargs) -> None:
    getattr(logger, level)(message, **kwargs)
